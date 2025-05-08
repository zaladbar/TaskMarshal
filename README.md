# Productivity Boss App

**Productivity Boss** is a cross-platform desktop application that acts as your autonomous productivity "boss". It combines an Electron-based frontend with a Python backend to monitor your computer usage (via ActivityWatch), provide real-time feedback, and deliver end-of-day performance reports in the style of a persona you choose.

## Features

- **Morning Planning:** Launches at system startup and prompts you each morning to enter your daily goals and select a boss persona (e.g., Coach Carter, Mr. Rogers, Chill Buddy, Motivational Guru).
- **Real-Time Monitoring:** Uses ActivityWatch to track active application usage and idle time in real-time, classifying activities into "Work" (productive) vs "Distraction" categories.
- **Persona-based Feedback:** Generates encouraging or corrective nudges throughout the day based on your persona choice. For example, Coach Carter might sternly push you to focus, while Mr. Rogers offers gentle encouragement.
- **End-of-Day Report:** Summarizes your work vs distraction time and goal progress. It uses the OpenAI API to produce a personalized report/commentary from your chosen persona.
- **Local Data & Privacy:** All detailed activity data stays local. Only a summarized version of your day's stats (e.g., total focus time, total distraction time, and your goals) is sent to the OpenAI API for generating the persona's report. The app stores daily logs and your preferences (including your OpenAI API key) securely on your machine. On first use, it asks for your consent to process and summarize your data.

## Installation & Setup

1. **Prerequisites:** Install [Node.js](https://nodejs.org) (which includes NPM) and Python 3 on your system. Also, install [ActivityWatch](https://activitywatch.net/docs/) and start it (the app expects the ActivityWatch server to be running on the default localhost port).
2. **Clone the Repository:** Clone this repository and navigate into it.
3. **Install Dependencies:** 
   - Frontend (Electron): Run `npm install` to install the Node.js/Electron packages.
   - Backend (Python): Install Python dependencies with `pip install -r backend/requirements.txt`.
4. **Configure OpenAI API Key:** Copy `config_example.json` to `config.json` (listed in .gitignore so it won't be committed) and insert your OpenAI API key. *Alternatively*, you can set an environment variable `OPENAI_API_KEY` with your key, and the app will use that.
5. **First Run & Consent:** Start the application. On first run, you'll be asked to consent to the use of summarized data for generating the AI feedback. The app will then prompt for your daily goals and persona selection.

## Running the App

- **Development Mode:** You can start the Electron app with `npm start`. This will launch the Python backend and then open the GUI. Make sure the ActivityWatch server is running before starting the app.
- **Production Build:** To package the app for distribution (so it can auto-start on login, etc.), you may use a tool like Electron Forge or Electron Builder (not included in this codebase). Ensure the Python backend (including necessary libraries) is packaged with the app or otherwise accessible.
- **Note:** On Linux, auto-launch at login may require additional setup (like creating a .desktop file in `~/.config/autostart`) as Electron's auto-launch is only directly supported on Windows and macOS.

## Usage

- **Morning Goals Input:** Each morning when the app launches, enter your main goals for the day in the text field provided and choose one of the boss personas. Click "Start Day" to begin the session.
- **Real-Time Feedback:** Once started, the app runs in the background (and in the system tray if minimized). It continuously monitors your activity. The main window (if opened) will show live stats: how much time you've spent on work vs distractions, and may display messages from your chosen persona. For instance, if you spend too long on distracting websites, your persona will pop up with a nudge.
- **End of Day Report:** When your day is over (or at any time you choose to wrap up), click "End Day" in the app. The app will compile your stats and ask OpenAI's API to generate a report in the voice of your chosen persona. You'll see a summary of your productivity and a personalized message (e.g., words of praise or advice). This report is also saved to the local log.
- **Data & Privacy:** Your detailed activity data never leaves your machine. Only summary statistics (total time on work vs play, and your written goals) are sent to OpenAI. The first-time consent dialog explains this. All data is stored under `backend/data/` on your machine:
   - `prefs.json` holds your preferences (like last chosen persona, consent flag, etc.) and does **not** include your API key (which is stored separately in `config.json` or environment).
   - `logs.json` accumulates daily summaries of your sessions for your reference.

## Extending Personas

Persona definitions are stored in `backend/personas.json`. You can edit this file to adjust personas or add new ones. Each persona has a name, an icon (emoji or path to an image in `frontend/assets`), a description prompt for the AI, and some preset messages. If adding a new persona, you'll also want to add an avatar image (optional) and restart the app.

## Basic Architecture

- **Electron Frontend:** Presents the GUI, handles user input (goals, persona selection, buttons), and displays feedback. Communicates with the backend via HTTP (to `localhost`).
- **Python Backend:** Runs a local web server (Flask) exposing endpoints for the frontend:
  - `/api/personas` (GET) – returns persona options.
  - `/api/prefs` (GET) – returns user preferences (e.g., whether consent given, last persona).
  - `/api/consent` (POST) – to record user consent.
  - `/api/start_day` (POST) – to start a session with given goals and persona.
  - `/api/status` (GET) – returns current productivity stats and any persona message/nudge.
  - `/api/end_day` (GET) – ends the session and returns the final report.
- **ActivityWatch Integration:** The backend connects to ActivityWatch (which must be running locally) to fetch active window and AFK (away-from-keyboard) data. It classifies each window event as "Work" or "Distraction" using predefined lists (and can use ActivityWatch categories if available). Idle time is computed from AFK data.
- **OpenAI Integration:** The backend uses the OpenAI API (ChatGPT model) for generating persona commentary. It sends only the summary of your day and persona description to the API. The actual API key is never exposed to the frontend or anywhere else.
- **Data Storage:** The backend writes your daily session summary to `logs.json` at end of day. Preferences (like last persona used and consent) are saved in `prefs.json`. The OpenAI API key is stored in `config.json` (which you should keep safe) or read from an environment variable.

## Running Tests

*(For brevity, test scripts are not included in this codebase, but you can manually test the app by running through a day cycle: start the app, simulate work/distraction (ActivityWatch must capture some data), then end the day to see the report.)