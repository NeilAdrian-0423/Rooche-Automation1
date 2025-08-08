# Calendar-Integrated ShareX Monitor

A modular Python application that integrates calendar events with ShareX screen recording and automatic audio transcription.

## Features

- 📅 **Calendar Integration**: Automatically fetch and display upcoming meetings
- 🎥 **ShareX Integration**: Automatic screen recording with keyboard shortcuts
- 🎯 **Audio Transcription**: Local Whisper-based transcription of recordings
- 🔄 **Webhook Support**: Send transcriptions and meeting data to webhooks
- ✅ **Pass/Fail Reporting**: Report meeting outcomes without recordings
- 📁 **Manual Processing**: Process previously recorded files

## Project Structure

project/
├── main.py                 # Entry point
├── core/                   # Core configuration and constants
│   ├── config.py          # Configuration management
│   ├── logging_config.py  # Logging setup
│   └── constants.py       # Application constants
├── services/              # Business logic services
│   ├── audio_processor.py    # Audio extraction and transcription
│   ├── calendar_service.py   # Calendar event fetching
│   ├── sharex_service.py     # ShareX integration
│   ├── webhook_service.py    # Webhook communication
│   └── monitoring_service.py # File monitoring
├── gui/                   # User interface
│   ├── main_window.py     # Main application window
│   ├── calendar_tab.py    # Calendar events tab
│   ├── manual_tab.py      # Manual file selection tab
│   └── dialogs.py         # Dialog windows
└── utils/                 # Utility functions
└── helpers.py         # Helper functions


## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
3. Copy .env.example to .env and configure your webhook URLs
4. Run the application:
  ```bash
    python main.py

## Configuration
The application stores configuration in config.json and uses environment variables from .env:

WEBHOOK_URL: Main webhook for transcription data
WEBHOOK_URL2: Webhook for fetching calendar events
ShareX history path (configured via GUI)
Whisper model and device settings
Usage
Calendar Events Tab
Click "Refresh Calendar Events" to load meetings
Select a meeting (upcoming meetings are auto-selected)
Verify auto-filled Notion URL and description
Click "Start Monitoring + Recording" to begin
Manual Files Tab
Use this tab to process previously recorded files:

Refresh the file list
Select a file
Click "Process Selected File"
Pass/Fail Reporting
Report meeting outcomes without recordings:

Fill in meeting details
Click "Submit Pass/Fail Result"
Select outcome and provide reason
Requirements
Python 3.8+
FFmpeg (for audio extraction)
ShareX (for screen recording)
pynput (optional, for keyboard shortcuts)