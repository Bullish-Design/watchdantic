#!/usr/bin/env python3
# /// script
# dependencies = [
#     "watchdantic>=0.2.1",
#     "pydantic>=2.0.0",
#     "PyYAML>=6.0.0",
#     "tomli>=2.0.0; python_version < '3.11'",
# ]
# ///
"""
Markdown Blog Post Watcher Example

This script demonstrates how to use Watchdantic to monitor Markdown files with
frontmatter for a blog or documentation system.

Usage:
    uv run example_markdown_watcher.py

The script will:
1. Create example blog posts with YAML/TOML frontmatter
2. Set up a watcher for *.md files
3. Process posts when they change (validate metadata, extract content)
4. Demonstrate blog post publishing workflow
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List
from datetime import datetime

from pydantic import BaseModel, Field
from watchdantic import Watchdantic, WatchdanticConfig


class BlogPost(BaseModel):
    """Blog post model with frontmatter metadata and content."""
    title: str
    author: str
    slug: str = ""
    tags: list[str] = Field(default_factory=list)
    category: str = "general"
    published: bool = False
    draft: bool = True
    created_at: str = ""
    updated_at: str = ""
    content: str = ""
    
    def model_post_init(self, __context) -> None:
        """Auto-generate slug and timestamps if not provided."""
        if not self.slug:
            self.slug = self.title.lower().replace(" ", "-").replace("'", "")
        
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


def main() -> None:
    print("📝 Markdown Blog Watcher Example")
    print("=" * 40)
    
    # Create blog directory structure
    blog_dir = Path("./blog_example")
    posts_dir = blog_dir / "posts"
    drafts_dir = blog_dir / "drafts"
    
    posts_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(exist_ok=True)
    
    # Initialize Watchdantic
    w = Watchdantic(
        WatchdanticConfig(
            default_debounce=0.5,
            enable_logging=True,
            log_level="INFO",
        )
    )
    
    # Track processed posts
    processed_posts: dict[str, BlogPost] = {}

    @w.triggers_on(BlogPost, "**/*.md", debounce=0.3)
    def handle_blog_post(posts: List[BlogPost], file_path: Path) -> None:
        """Process blog post changes."""
        post = posts[0]  # Markdown files contain single post
        
        print(f"\n📄 Processing: {file_path.name}")
        print(f"   Title: {post.title}")
        print(f"   Author: {post.author}")
        print(f"   Tags: {', '.join(post.tags) if post.tags else 'None'}")
        print(f"   Status: {'Published' if post.published else 'Draft'}")
        
        # Store processed post
        processed_posts[str(file_path)] = post
        
        # Simulate blog processing logic
        if post.published and not post.draft:
            print(f"   🚀 PUBLISHED: Ready for live site!")
            # Here you might copy to public folder, trigger rebuild, etc.
        elif post.draft:
            print(f"   ✏️  DRAFT: Still being edited")
        else:
            print(f"   📋 READY: Approved but not published")
        
        # Check content length
        word_count = len(post.content.split()) if post.content else 0
        print(f"   📊 Word count: {word_count}")
        
        if word_count < 100 and not post.draft:
            print(f"   ⚠️  WARNING: Post might be too short for publication")

    # Create example blog posts
    example_posts = [
        BlogPost(
            title="Getting Started with Python",
            author="Alice Developer",
            tags=["python", "tutorial", "beginner"],
            category="tutorials",
            published=False,
            draft=True,
            content="""# Getting Started with Python

Python is a versatile programming language that's perfect for beginners.

## Installation

First, visit python.org to download Python for your system.

## Your First Program

```python
print("Hello, World!")
```

This simple program demonstrates Python's readable syntax.
"""
        ),
        
        BlogPost(
            title="Advanced Pydantic Patterns",
            author="Bob Expert", 
            tags=["python", "pydantic", "advanced"],
            category="advanced",
            published=True,
            draft=False,
            content="""# Advanced Pydantic Patterns

Pydantic provides powerful data validation capabilities.

## Custom Validators

You can create custom validation logic:

```python
from pydantic import BaseModel, validator

class User(BaseModel):
    name: str
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.title()
```

## Model Composition

Complex models can be built from simpler ones:

```python
class Address(BaseModel):
    street: str
    city: str
    
class User(BaseModel):
    name: str
    address: Address
```
"""
        )
    ]
    
    # Write example posts
    for i, post in enumerate(example_posts):
        filename = f"post_{i+1}.md" if not post.draft else f"draft_{i+1}.md"
        target_dir = posts_dir if not post.draft else drafts_dir
        file_path = target_dir / filename
        
        print(f"\n📝 Creating: {file_path}")
        w.write_models([post], file_path)
    
    # Start watching
    print(f"\n👀 Watching for Markdown changes in: {blog_dir}")
    print("   Try editing the .md files to see live processing!")
    print("   Change 'published: true' to see publication workflow")
    print("   Press Ctrl+C to exit")
    
    w.start(blog_dir)
    
    try:
        time.sleep(2)
        
        # Demonstrate automatic post promotion
        print(f"\n🔄 Demonstrating post promotion...")
        
        if processed_posts:
            # Find a draft post to publish
            for file_path_str, post in processed_posts.items():
                if post.draft:
                    print(f"   Promoting draft: {post.title}")
                    
                    # Update post status
                    updated_post = post.model_copy(deep=True)
                    updated_post.draft = False
                    updated_post.published = True
                    updated_post.updated_at = datetime.now().isoformat()
                    
                    # Move from drafts to posts
                    old_path = Path(file_path_str)
                    new_path = posts_dir / old_path.name
                    
                    # Write to new location
                    w.write_models([updated_post], new_path)
                    
                    # Remove old draft (in real app, you'd handle this more carefully)
                    if old_path.exists():
                        old_path.unlink()
                    
                    break
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Shutting down blog watcher...")
        w.stop()
        print("   Blog processing complete!")


if __name__ == "__main__":
    main()