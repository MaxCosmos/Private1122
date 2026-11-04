from pathlib import Path

root = Path("iceraven-src")
screen = root / "app/src/main/java/org/mozilla/fenix/bookmarks/BookmarksScreen.kt"
text = screen.read_text()

for item in ["import android.widget.Toast", "import androidx.compose.ui.platform.LocalContext"]:
    if item not in text:
        anchor = "import android.view.ViewGroup\n"
        text = text.replace(anchor, anchor + item + "\n", 1)

old = """private fun RootBookmarksOverflowMenu(store: BookmarksStore) {
    val showMenu by remember {
        store.stateFlow.map { store.state.rootMenuShown }
    }
        .collectAsState(initial = store.state.rootMenuShown)

    val menuItems =
        listOf(
            MenuItem.TextItem(
                text = Text.Resource(R.string.bookmark_import_menu_button),
                onClick = { store.dispatch(ImportAction.ImportFileClicked.FromMenu) },
            )
        )

    DropdownMenu(
        menuItems = menuItems,
        expanded = showMenu,
        onDismissRequest = { store.dispatch(RootOverflowMenuDismissed) },
    )
}"""
new = """private fun RootBookmarksOverflowMenu(store: BookmarksStore) {
    val showMenu by remember {
        store.stateFlow.map { store.state.rootMenuShown }
    }
        .collectAsState(initial = store.state.rootMenuShown)
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun export(format: BookmarkExportFormat) {
        scope.launch {
            runCatching { exportBookmarks(context, format) }
                .onSuccess {
                    Toast.makeText(context, "Bookmarks exported to Downloads", Toast.LENGTH_LONG).show()
                }
                .onFailure {
                    Toast.makeText(context, "Bookmark export failed: \${it.localizedMessage ?: "unknown error"}", Toast.LENGTH_LONG).show()
                }
        }
    }

    val menuItems =
        listOf(
            MenuItem.TextItem(
                text = Text.Resource(R.string.bookmark_import_menu_button),
                onClick = { store.dispatch(ImportAction.ImportFileClicked.FromMenu) },
            ),
            MenuItem.TextItem(
                text = Text.Resource(R.string.bookmark_export_html_menu_button),
                onClick = { export(BookmarkExportFormat.HTML) },
            ),
            MenuItem.TextItem(
                text = Text.Resource(R.string.bookmark_export_json_menu_button),
                onClick = { export(BookmarkExportFormat.JSON) },
            ),
        )

    DropdownMenu(
        menuItems = menuItems,
        expanded = showMenu,
        onDismissRequest = { store.dispatch(RootOverflowMenuDismissed) },
    )
}"""
if old not in text:
    raise SystemExit("Could not locate RootBookmarksOverflowMenu.")
screen.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle"
g = gradle.read_text()
if 'applicationId "io.github.forkmaintainers"' not in g:
    raise SystemExit("Could not locate app ID.")
gradle.write_text(g.replace('applicationId "io.github.forkmaintainers"', 'applicationId "io.github.maxcosmos.iceravenexport"', 1))

strings = root / "app/src/main/res/values/strings.xml"
st = strings.read_text()
if "</resources>" not in st:
    raise SystemExit("Could not locate resources closing tag.")
add = """    <string name="bookmark_export_html_menu_button">Export bookmarks (HTML)</string>
    <string name="bookmark_export_json_menu_button">Export bookmarks (JSON)</string>
"""
if "bookmark_export_html_menu_button" not in st:
    strings.write_text(st.replace("</resources>", add + "</resources>", 1))

exporter = root / "app/src/main/java/org/mozilla/fenix/bookmarks/BookmarkExporter.kt"
exporter.write_text(r'''/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.fenix.bookmarks

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mozilla.appservices.places.BookmarkRoot
import mozilla.components.concept.storage.BookmarkNode
import mozilla.components.concept.storage.BookmarkNodeType
import org.json.JSONArray
import org.json.JSONObject
import org.mozilla.fenix.ext.bookmarkStorage

internal enum class BookmarkExportFormat { HTML, JSON }

internal suspend fun exportBookmarks(context: Context, format: BookmarkExportFormat) {
    withContext(Dispatchers.IO) {
        val root = context.bookmarkStorage
            .getTree(BookmarkRoot.Root.id, recursive = true)
            .getOrThrow() ?: error("Bookmark root is unavailable")

        val extension = if (format == BookmarkExportFormat.HTML) "html" else "json"
        val mimeType = if (format == BookmarkExportFormat.HTML) "text/html" else "application/json"
        val content = if (format == BookmarkExportFormat.HTML) buildHtml(root) else buildJson(root).toString(2)

        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, "iceraven-bookmarks-\${System.currentTimeMillis()}.$extension")
            put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            }
        }
        val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Downloads.EXTERNAL_CONTENT_URI
        } else {
            MediaStore.Files.getContentUri("external")
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(collection, values) ?: error("Could not create export file")
        try {
            val output = resolver.openOutputStream(uri) ?: error("Could not open export file")
            output.bufferedWriter(Charsets.UTF_8).use { it.write(content) }
        } catch (error: Throwable) {
            resolver.delete(uri, null, null)
            throw error
        }
    }
}

private fun buildHtml(root: BookmarkNode): String = buildString {
    appendLine("<!DOCTYPE NETSCAPE-Bookmark-file-1>")
    appendLine("""<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">""")
    appendLine("<TITLE>Bookmarks</TITLE>")
    appendLine("<H1>Bookmarks</H1>")
    appendLine("<DL><p>")
    root.children.orEmpty().forEach { appendHtmlNode(it, 1) }
    appendLine("</DL><p>")
}

private fun StringBuilder.appendHtmlNode(node: BookmarkNode, depth: Int) {
    val indent = "    ".repeat(depth)
    when (node.type) {
        BookmarkNodeType.FOLDER -> {
            append(indent).append("<DT><H3>")
                .append(escapeHtml(node.title.orEmpty()))
                .appendLine("</H3>")
            append(indent).appendLine("<DL><p>")
            node.children.orEmpty().forEach { appendHtmlNode(it, depth + 1) }
            append(indent).appendLine("</DL><p>")
        }
        BookmarkNodeType.ITEM -> {
            val url = node.url ?: return
            append(indent).append("<DT><A HREF=\"")
                .append(escapeHtmlAttribute(url))
                .append("\" ADD_DATE=\"").append(node.dateAdded / 1000)
                .append("\">").append(escapeHtml(node.title ?: url))
                .appendLine("</A>")
        }
        BookmarkNodeType.SEPARATOR -> append(indent).appendLine("<HR>")
    }
}

private fun escapeHtml(value: String): String =
    value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

private fun escapeHtmlAttribute(value: String): String =
    escapeHtml(value).replace("\"", "&quot;").replace("'", "&#39;")

private fun buildJson(node: BookmarkNode): JSONObject = JSONObject().apply {
    put("type", node.type.name.lowercase())
    put("guid", node.guid)
    put("title", node.title ?: JSONObject.NULL)
    put("url", node.url ?: JSONObject.NULL)
    put("dateAdded", node.dateAdded)
    put("lastModified", node.lastModified)
    val children = JSONArray()
    node.children.orEmpty().forEach { children.put(buildJson(it)) }
    put("children", children)
}
''')
print("Patch script ready")
