from __future__ import annotations

import pytest
from pathlib import Path
from pydantic import BaseModel, ValidationError

from watchdantic.formats.markdown import MarkdownWithFrontmatter, MarkdownFile
from watchdantic.exceptions import FileFormatError


class BlogPost(BaseModel):
    title: str
    author: str
    tags: list[str] = []
    published: bool = False
    content: str = ""


class SimplePost(BaseModel):
    title: str
    content: str = ""


class ContentOnly(BaseModel):
    content: str


class TextDocument(BaseModel):
    text: str


class TestMarkdownFile:
    """Test the base MarkdownFile handler (plain markdown)."""

    def test_get_extension(self):
        handler = MarkdownFile()
        assert handler.get_extension() == ".md"

    def test_parse_plain_markdown_with_content_field(self):
        handler = MarkdownFile()
        content = """# Just a Title

Regular markdown content without frontmatter.
"""

        models = handler.parse(content, ContentOnly)
        assert len(models) == 1
        assert models[0].content == content.strip()

    def test_parse_plain_markdown_with_text_field(self):
        handler = MarkdownFile()
        content = """# Document Title

Some markdown text here.
"""

        models = handler.parse(content, TextDocument)
        assert len(models) == 1
        assert models[0].text == content.strip()

    def test_parse_plain_markdown_incompatible_model(self):
        handler = MarkdownFile()
        content = """# Just a Title

Regular markdown content.
"""

        # Model requires title and author, but we only have plain text
        models = handler.parse(content, BlogPost)
        assert len(models) == 0

    def test_parse_empty_content(self):
        handler = MarkdownFile()
        models = handler.parse("", ContentOnly)
        assert models == []

    def test_write_content_field(self):
        handler = MarkdownFile()
        model = ContentOnly(content="# Hello\n\nWorld")

        result = handler.write([model])
        assert result == "# Hello\n\nWorld"

    def test_write_text_field(self):
        handler = MarkdownFile()
        model = TextDocument(text="Some text content")

        result = handler.write([model])
        assert result == "Some text content"


class TestMarkdownWithFrontmatter:
    """Test the MarkdownWithFrontmatter handler."""

    def test_get_extension(self):
        handler = MarkdownWithFrontmatter()
        assert handler.get_extension() == ".md"

    def test_parse_yaml_frontmatter(self):
        handler = MarkdownWithFrontmatter()
        content = """---
title: "Hello World"
author: "John Doe"
tags: ["python", "markdown"]
published: true
---

# Hello World

This is my first blog post!
"""

        models = handler.parse(content, BlogPost)
        assert len(models) == 1

        model = models[0]
        assert model.title == "Hello World"
        assert model.author == "John Doe"
        assert model.tags == ["python", "markdown"]
        assert model.published is True
        assert "# Hello World" in model.content

    def test_parse_toml_frontmatter(self):
        handler = MarkdownWithFrontmatter()
        content = """+++
title = "Hello TOML"
author = "Jane Doe"
tags = ["rust", "toml"]
published = false
+++

# Hello TOML

This post uses TOML frontmatter.
"""

        models = handler.parse(content, BlogPost)
        assert len(models) == 1

        model = models[0]
        assert model.title == "Hello TOML"
        assert model.author == "Jane Doe"
        assert model.tags == ["rust", "toml"]
        assert model.published is False
        assert "# Hello TOML" in model.content

    def test_parse_no_frontmatter_content_only_model(self):
        """Plain markdown should work with content-only models."""
        handler = MarkdownWithFrontmatter()
        content = """# Just a Title

Regular markdown content without frontmatter.
"""

        models = handler.parse(content, ContentOnly)
        assert len(models) == 1
        assert models[0].content == content.strip()

    def test_parse_no_frontmatter_complex_model(self):
        """Plain markdown should fail gracefully with complex models."""
        handler = MarkdownWithFrontmatter()
        content = """# Just a Title

Regular markdown content without frontmatter.
"""

        # BlogPost requires title and author, plain markdown can't provide these
        models = handler.parse(content, BlogPost)
        assert len(models) == 0

    def test_parse_frontmatter_validation_fails_fallback_works(self):
        """Invalid frontmatter should fall back to plain markdown parsing for compatible models."""
        handler = MarkdownWithFrontmatter()
        content = """---
title: 
  nested: "object"  # dict where string expected - will fail validation
author: "John"
---

# Content Title

Some content here.
"""

        # Test with ContentOnly model - fallback should succeed
        models = handler.parse(content, ContentOnly)
        print(f"\n\nContent Only: {models}\n\n")
        models2 = handler.parse(content, BlogPost)
        print(f"\n\nSimple Post: {models2}\n\n")
        # models3 = handler.parse(content)
        # print(f"\n\nBlog Post: {models3}\n\n")
        assert len(models) == 1
        # Should fall back to plain markdown and include entire content
        assert 'nested: "object"' in models[0].content
        assert "Some content here" in models[0].content

    def test_parse_frontmatter_validation_fails_no_fallback_for_complex_models(self):
        """Invalid frontmatter with complex models should return empty when fallback also fails."""
        handler = MarkdownWithFrontmatter()
        content = """---
title: 
  nested: "object"  # dict where string expected
author: "John"
---

# Content Title

Some content here.
"""

        # BlogPost requires title and author - fallback to plain markdown will also fail
        models = handler.parse(content, BlogPost)
        assert len(models) == 0

    def test_parse_empty_content(self):
        handler = MarkdownWithFrontmatter()
        models = handler.parse("", BlogPost)
        assert models == []

    def test_parse_invalid_yaml_frontmatter(self):
        handler = MarkdownWithFrontmatter()
        content = """---
title: "Missing quote
author: John
---

Content here
"""

        with pytest.raises(FileFormatError, match="Invalid YAML frontmatter"):
            handler.parse(content, BlogPost)

    def test_parse_invalid_toml_frontmatter(self):
        handler = MarkdownWithFrontmatter()
        content = """+++
title = "Missing quote
author = "John"
+++

Content here
"""

        with pytest.raises(FileFormatError, match="Invalid TOML frontmatter"):
            handler.parse(content, BlogPost)

    def test_write_with_frontmatter_and_content(self):
        handler = MarkdownWithFrontmatter()
        model = BlogPost(
            title="Test Post",
            author="Test Author",
            tags=["test", "example"],
            published=True,
            content="# Test\n\nThis is test content.",
        )

        result = handler.write([model])

        assert result.startswith("---\n")
        assert "title: Test Post" in result
        assert "author: Test Author" in result
        assert "tags:" in result
        assert "- test" in result
        assert "- example" in result
        assert "published: true" in result
        assert "---\n\n# Test\n\nThis is test content." in result

    def test_write_content_only_no_frontmatter(self):
        """Models with only content and no other meaningful data should write plain markdown."""
        handler = MarkdownWithFrontmatter()
        model = ContentOnly(content="Just plain content")

        result = handler.write([model])
        assert result == "Just plain content"

    def test_write_meaningful_metadata_includes_frontmatter(self):
        """Models with meaningful metadata should include frontmatter."""
        handler = MarkdownWithFrontmatter()
        model = BlogPost(
            title="Real Title",  # Meaningful
            author="Real Author",  # Meaningful
            tags=["test"],  # Meaningful
            published=True,  # Meaningful
            content="Content here",
        )

        result = handler.write([model])
        assert result.startswith("---")
        assert "title: Real Title" in result

    def test_write_some_empty_some_meaningful_includes_frontmatter(self):
        """Models with some meaningful metadata should include frontmatter."""
        handler = MarkdownWithFrontmatter()
        model = BlogPost(
            title="",  # Empty
            author="Real Author",  # Meaningful
            tags=[],  # Empty
            published=False,  # Default but will be included since author is meaningful
            content="Content here",
        )

        result = handler.write([model])
        # Should include frontmatter because author is meaningful
        assert result.startswith("---")
        assert "author: Real Author" in result

    def test_write_empty_models(self):
        handler = MarkdownWithFrontmatter()
        result = handler.write([])
        assert result == ""

    def test_write_multiple_models_uses_first(self):
        handler = MarkdownWithFrontmatter()
        model1 = ContentOnly(content="First content")
        model2 = ContentOnly(content="Second content")

        result = handler.write([model1, model2])

        assert "First content" in result
        assert "Second content" not in result

    def test_read_models_from_file(self, tmp_path: Path):
        handler = MarkdownWithFrontmatter()

        # Create test markdown file
        test_file = tmp_path / "test.md"
        test_file.write_text("""---
title: "File Test"
author: "File Author"
published: true
---

# File Content

This content was read from a file.
""")

        models = handler.read_models(test_file, BlogPost)
        assert len(models) == 1

        model = models[0]
        assert model.title == "File Test"
        assert model.author == "File Author"
        assert model.published is True
        assert "# File Content" in model.content

    def test_read_models_file_not_found(self, tmp_path: Path):
        handler = MarkdownWithFrontmatter()
        missing_file = tmp_path / "missing.md"

        with pytest.raises(FileFormatError, match="Failed to read file"):
            handler.read_models(missing_file, BlogPost)

    def test_write_requires_pyyaml(self, monkeypatch):
        # Mock yaml as None to test error handling
        import watchdantic.formats.markdown as markdown_module

        monkeypatch.setattr(markdown_module, "yaml", None)

        handler = MarkdownWithFrontmatter()
        model = BlogPost(title="test", author="author")

        with pytest.raises(FileFormatError, match="PyYAML package is required"):
            handler.write([model])

    def test_parse_requires_pyyaml_for_yaml_frontmatter(self, monkeypatch):
        # Mock yaml as None
        import watchdantic.formats.markdown as markdown_module

        monkeypatch.setattr(markdown_module, "yaml", None)

        handler = MarkdownWithFrontmatter()
        content = """---
title: "Test"
---
Content"""

        with pytest.raises(FileFormatError, match="PyYAML package is required"):
            handler.parse(content, BlogPost)

    def test_frontmatter_detection(self):
        handler = MarkdownWithFrontmatter()

        # YAML frontmatter should be detected
        yaml_content = "---\ntitle: test\n---\ncontent"
        assert handler._has_frontmatter(yaml_content) is True

        # TOML frontmatter should be detected
        toml_content = "+++\ntitle = 'test'\n+++\ncontent"
        assert handler._has_frontmatter(toml_content) is True

        # Plain markdown should not be detected as having frontmatter
        plain_content = "# Title\n\nContent"
        assert handler._has_frontmatter(plain_content) is False

        # Content starting with dashes but not proper frontmatter
        fake_content = "--- this is not frontmatter\ncontent"
        assert handler._has_frontmatter(fake_content) is False

    def test_frontmatter_without_content_field(self):
        class MetadataOnly(BaseModel):
            title: str
            author: str

        handler = MarkdownWithFrontmatter()
        content = """---
title: "Metadata Only"
author: "Test Author"
---

This content won't be included since model has no content field.
"""

        models = handler.parse(content, MetadataOnly)
        assert len(models) == 1

        model = models[0]
        assert model.title == "Metadata Only"
        assert model.author == "Test Author"
        # content field should not exist

