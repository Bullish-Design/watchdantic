#!/usr/bin/env python3
# /// script
# dependencies = [
#     "watchdantic>=0.2.1",
#     "pydantic>=2.0.0",
# ]
# ///
"""
Text Log Processing Example

This script demonstrates how to use Watchdantic to monitor and process plain text files
like logs, notes, or simple documents.

Usage:
    uv run example_txt_watcher.py

The script will:
1. Create example text files (logs, notes, reports)
2. Set up watchers for different .txt patterns
3. Process and analyze text content automatically
4. Demonstrate text file classification and routing
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from watchdantic import Watchdantic, WatchdanticConfig


class LogEntry(BaseModel):
    """Log file content model."""
    content: str
    
    @property
    def line_count(self) -> int:
        return len(self.content.splitlines()) if self.content else 0
    
    @property
    def error_count(self) -> int:
        return self.content.lower().count('error') if self.content else 0
    
    @property
    def warning_count(self) -> int:
        return self.content.lower().count('warning') if self.content else 0


class NoteDocument(BaseModel):
    """Personal note or document model."""
    content: str
    
    @property
    def word_count(self) -> int:
        return len(self.content.split()) if self.content else 0
    
    @property
    def has_todo(self) -> bool:
        return 'TODO' in self.content.upper() if self.content else False


class ReportDocument(BaseModel):
    """Report or analysis document model."""
    content: str
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        if v and len(v.strip()) < 50:
            raise ValueError("Report content too short (minimum 50 characters)")
        return v
    
    @property
    def section_count(self) -> int:
        return self.content.count('##') if self.content else 0


def main() -> None:
    print("📄 Text File Processing Example")
    print("=" * 35)
    
    # Create directory structure
    text_dir = Path("./text_processing_example")
    logs_dir = text_dir / "logs"
    notes_dir = text_dir / "notes"  
    reports_dir = text_dir / "reports"
    
    for dir_path in [logs_dir, notes_dir, reports_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize Watchdantic
    w = Watchdantic(
        WatchdanticConfig(
            default_debounce=0.3,
            enable_logging=True,
            log_level="INFO",
        )
    )

    @w.triggers_on(LogEntry, "logs/*.txt", debounce=0.2)
    def handle_log_file(logs: List[LogEntry], file_path: Path) -> None:
        """Process log files for monitoring and alerting."""
        log = logs[0]
        
        print(f"\n🔍 LOG ANALYSIS: {file_path.name}")
        print(f"   Lines: {log.line_count}")
        print(f"   Errors: {log.error_count}")
        print(f"   Warnings: {log.warning_count}")
        
        # Alert on issues
        if log.error_count > 0:
            print(f"   🚨 ALERT: {log.error_count} errors detected!")
        elif log.warning_count > 5:
            print(f"   ⚠️  WARNING: {log.warning_count} warnings found")
        else:
            print(f"   ✅ Status: Log looks healthy")

    @w.triggers_on(NoteDocument, "notes/*.txt", debounce=0.2) 
    def handle_note_file(notes: List[NoteDocument], file_path: Path) -> None:
        """Process personal notes and documents."""
        note = notes[0]
        
        print(f"\n📝 NOTE UPDATE: {file_path.name}")
        print(f"   Words: {note.word_count}")
        
        if note.has_todo:
            print(f"   ✏️  Contains TODO items")
        
        # Categorize by length
        if note.word_count > 500:
            print(f"   📚 Category: Long-form document")
        elif note.word_count > 100:
            print(f"   📄 Category: Standard note") 
        elif note.word_count > 0:
            print(f"   📃 Category: Quick note")
        else:
            print(f"   📋 Category: Empty/template")

    @w.triggers_on(ReportDocument, "reports/*.txt", debounce=0.5, continue_on_error=True)
    def handle_report_file(reports: List[ReportDocument], file_path: Path) -> None:
        """Process formal reports with validation."""
        report = reports[0] 
        
        print(f"\n📊 REPORT PROCESSED: {file_path.name}")
        print(f"   Sections: {report.section_count}")
        print(f"   Length: {len(report.content)} characters")
        
        # Quality checks
        if report.section_count == 0:
            print(f"   📋 Format: Plain text report")
        else:
            print(f"   📋 Format: Structured report")
            
        print(f"   ✅ Report validation passed")

    # Create example files
    example_files = [
        # Log files
        (logs_dir / "app.txt", LogEntry(
            content="""2024-01-15 10:00:01 INFO  Application started
2024-01-15 10:00:05 INFO  Database connected
2024-01-15 10:01:23 WARNING Connection pool nearly full  
2024-01-15 10:02:15 ERROR Failed to process request: timeout
2024-01-15 10:02:16 INFO  Retrying request
2024-01-15 10:02:18 INFO  Request processed successfully
2024-01-15 10:03:00 INFO  Heartbeat sent"""
        )),
        
        # Note files
        (notes_dir / "meeting.txt", NoteDocument(
            content="""Team Meeting Notes - January 15, 2024

Attendees: Alice, Bob, Charlie

Agenda:
- Project status update
- New feature requirements  
- TODO: Review API documentation
- Budget discussion

Action Items:
- Alice: Finish user authentication module
- Bob: TODO: Set up monitoring dashboard
- Charlie: Update deployment pipeline

Next meeting: January 22, 2024"""
        )),
        
        # Report files
        (reports_dir / "quarterly.txt", ReportDocument(
            content="""Q4 2023 Performance Report

## Executive Summary
The fourth quarter showed strong performance across all key metrics.

## Key Metrics
- Revenue: $2.5M (up 15% from Q3)
- Active Users: 50,000 (up 8%)
- Customer Satisfaction: 4.2/5.0

## Challenges
- Server capacity reaching limits
- Increased support ticket volume
- Competition in market segment

## Recommendations
1. Invest in infrastructure scaling
2. Expand customer support team
3. Accelerate product development cycle

## Conclusion
Strong quarter positions us well for 2024 growth."""
        ))
    ]
    
    # Write example files
    for file_path, model in example_files:
        print(f"\n📝 Creating: {file_path}")
        w.write_models([model], file_path)
    
    # Start watching
    print(f"\n👀 Watching text files in: {text_dir}")
    print("   Try editing the .txt files to see processing!")
    print("   Add 'ERROR' to logs to trigger alerts")
    print("   Add 'TODO' to notes for task detection")
    print("   Press Ctrl+C to exit")
    
    w.start(text_dir)
    
    try:
        time.sleep(2)
        
        # Demonstrate log alert generation
        print(f"\n🚨 Demonstrating log alert...")
        
        alert_log = LogEntry(
            content="""2024-01-15 10:05:00 ERROR Database connection lost
2024-01-15 10:05:01 ERROR Failed to save user data
2024-01-15 10:05:02 CRITICAL System entering degraded mode
2024-01-15 10:05:03 ERROR Authentication service unavailable"""
        )
        
        alert_file = logs_dir / "alert.txt"
        w.write_models([alert_log], alert_file)
        
        time.sleep(1)
        
        # Demonstrate note with TODOs
        print(f"\n📝 Adding TODO-rich note...")
        
        todo_note = NoteDocument(
            content="""Project Planning Notes

TODO: Review system architecture
TODO: Update documentation  
TODO: Schedule code review
TODO: Deploy to staging environment

Current blockers:
- Waiting for API keys
- Need database migration script

TODO: Follow up with security team about audit"""
        )
        
        todo_file = notes_dir / "project_plan.txt"
        w.write_models([todo_note], todo_file)
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Shutting down text processor...")
        w.stop()
        print("   Text processing complete!")


if __name__ == "__main__":
    main()