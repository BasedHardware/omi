package com.friend.ios.features.components

import com.friend.ios.features.components.MarkdownBlocks.Block
import org.junit.Assert.assertEquals
import org.junit.Test

class MarkdownBlocksTest {
    @Test
    fun parsesBlocksLikeIOS() {
        val text = """
            # Plan
            First line
            second line

            - one
              - nested
            2) two
            > Draft to Anna
            > line two
            | A | B |
            |---|:-:|
            | 1 | 2 |
            ```
            code here
        """.trimIndent()
        assertEquals(
            listOf(
                Block.Heading("Plan"),
                Block.Paragraph("First line\nsecond line"),
                Block.Bullet("one", 0),
                Block.Bullet("nested", 1),
                Block.Numbered("two", "2", 0),
                Block.Quote("Draft to Anna\nline two"),
                Block.Table(listOf(listOf("A", "B"), listOf("1", "2"))),
                Block.Code("code here"),
            ),
            MarkdownBlocks.parse(text),
        )
    }

    @Test
    fun inlineMarksBecomeSpansAndPlainTextStays() {
        val styled = inline("**Bold** and *it* `x` [link](https://omi.me) 2 * 3 * 4 snake_case_name", androidx.compose.ui.graphics.Color.Blue)
        assertEquals("Bold and it x link 2 * 3 * 4 snake_case_name", styled.text)
        assertEquals(3, styled.spanStyles.size)
        assertEquals(1, styled.getLinkAnnotations(0, styled.length).size)
    }
}
