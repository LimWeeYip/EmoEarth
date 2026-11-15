# 🌍 EmoEarth: NASA Earth Data as a 3D Globe with Music 

A project that downloads NASA Earth data, cleans it,
turns the colours and their change into orchestral music, and plays both together on an interactive 3D globe,
so you can hear and feel the Earth's mood change.
Three data layers, each with its own orchestra (pick one in the legend's menu, or press Z, X or C):
**ice surface temperature** (MODIS Terra, daily, 2026), **ocean currents and sea temperature** (ECCO2 model, 2007 to 2008)
and **carbon dioxide** (GEOS model, January to March 2020).
A spoken description (narration) and keyboard shortcuts make it usable for blind and low-vision listeners too.
It has a sign-in page (accounts, Firebase email and Google, or **Guest Only**), keeps a log and counts sign-ins,
and can be hosted on Microsoft Azure so everyone opens one web address.

This project is fully compatible with the following operating systems:
*   **macOS**
*   **Windows**

Browser Compatibility: Verified to work on the latest versions of Google Chrome, Microsoft Edge, and Apple Safari.

---

## 1. Data Sources

| Item | Source |
|---|---|
| Ice Surface Temperature | NASA Worldview (https://worldview.earthdata.nasa.gov); NASA GIBS (Global Imagery Browse Services), layer `MODIS_Terra_Ice_Surface_Temp_Day` (Terra / MODIS, v6.1 STD) |
| Data Retrieval | GIBS WMS service (`https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi`), no API key needed |
| Base map (optional) | GIBS layer `BlueMarble_NextGeneration` |
| Country borders | GIBS layer `DoS_International_Boundaries` (U.S. Department of State) if available as an image; otherwise Natural Earth country borders via the `world-atlas` package on the jsdelivr CDN |
| Coastlines | GIBS layer `Coastlines_15m` if available as an image; otherwise land outlines from Natural Earth (`world-atlas` on the jsdelivr CDN) |
| Color scale | 223.2 K to 313.2 K (about -50 °C to 40 °C) |
| Ocean layer (optional) | NASA/GSFC Scientific Visualization Studio 3912, "Global Sea Surface Currents and Temperature": ECCO2 model (MIT/JPL), 2007-03-25 to 2008-03-03, frames from https://svs.gsfc.nasa.gov/vis/a000000/a003900/a003912/frames/2048x1024_1x1_30p/ (see 5c) |
| Ocean colour scale | 0 °C (blue) to 32 °C (red), NASA's colour bar `sst_ecco2_cbar.png` |
| Carbon dioxide layer (optional) | NASA/GSFC Scientific Visualization Studio 5436, "DYAMOND Global Carbon Dioxide" (Science On a Sphere version of 5196): NASA GEOS model, 2020-01-14 to 2020-03-03, hourly frames from https://svs.gsfc.nasa.gov/vis/a000000/a005400/a005436/frames/8192x4096_2x1_30p/soscomp_1-29-2025a_pngs/ (see 5c) |
| Carbon dioxide colour scale | 380 to 460 ppm (`dyamondCbar_6-27-2024a.png`); see-through below about 425 ppm, then tan, orange and red |

Important: GIBS returns already-colored pictures, not raw temperature numbers.
Everything in this project that says "temperature" is estimated from the picture colors,
so it is good for trends and visuals, not for exact scientific measurements.

---

## 2. Tools and languages

| Purpose | Tool |
|---|---|
| Editor and terminal | VS Code |
| Backend, data processing, music synthesis | Python 3 |
| Web server | Flask (Python web framework, version 3 or newer) |
| 3D globe in the browser | JavaScript with Three.js (loaded from a CDN) |
| Rendering of the temperature layers on the globe | GLSL (a small shader written inside `index.html`) |
| Page layout and styling | HTML and CSS |
| Live sound analysis in the browser | Web Audio API (`AnalyserNode`) for the equalizer bars |
| Sound wave as tables | pandas (`export_wave.py`) |
| Writing the narration | Google Gemini (`narrate.py`, optional) |
| Speaking the narration | pyttsx3 to make `narration.wav`, or the browser's built-in voice (Web Speech API) |

Python packages (see `requirements.txt`):

| Package | Used for |
|---|---|
| flask | The web server that shows the 3D globe page (`app.py`) |
| requests | Downloading images and checking for new days from NASA GIBS |
| pillow | Reading, resizing and saving the images |
| numpy | Image processing, temperature and colour analysis, and synthesizing the orchestra |
| pandas | Sound wave tables (`export_wave.py`) |
| lameenc | Makes the compressed `music.mp3` the page plays (optional: without it the page plays `music.wav`) |
| matplotlib | Optional flat 2D animations |
| owslib | Optional GIBS (WMS) helper used by the download scripts |
| google-genai | Gemini writes the spoken narration (`narrate.py`) |
| pyttsx3 | Turns the narration text into `narration.wav` |
| sounddevice | Plays the music with the flat animation (`animate_ice_music.py`) |
| opencv-python | Image metrics in `narration.py` and `imgprocessing_darkspots_removal.py` |

All of them install with `python -m pip install -r requirements.txt`.

### Flask

Flask is a small Python web framework. In EmoEarth it runs a local web server on your own computer, so the browser can load the 3D globe page, the music and the data files.

Install (already included in `requirements.txt`):

```bash
python -m pip install flask          # or: python -m pip install -r requirements.txt
```

Start it with `python app.py`, then open http://127.0.0.1:5000. The server only listens on your own computer (127.0.0.1, port 5000) and stops when you close the terminal or press Ctrl+C.

| Address | What Flask returns |
|---|---|
| `/` | The globe page (`static/index.html`) |
| `/static/...` | The page's files: `data/music.mp3`, `data/timeline.json`, `data/frames/*.webp`, logos, `version.txt` |
| `/api/status` | JSON: latest data date, build time, and whether an update is running (the page asks every 15 seconds) |
| `/api/update` (POST) | Starts a check for new NASA data in the background (the "Check for new data" button) |

Options for `python app.py`:

| Option | What it does |
|---|---|
| `--rebuild` | Rebuild all frames and the music before starting |
| `--recalibrate` | Rebuild and reset the frozen pitch, tempo and colour ranges |
| `--auto-update 6` | Also check NASA for new data every 6 hours while the app runs |

Caching: frames and music are requested with a version number (`?v=...`), and every build gives them a new one. So `app.py` tells the browser to keep those files (for a year). The page, `timeline.json`, `narration.json` and `version.txt` are always checked again, so updates still show up straight away. A second visit therefore loads almost instantly.

The server uses Flask's built-in development server, which is fine for running EmoEarth on your own computer. To put it on the internet for other people, use a production server such as gunicorn or waitress instead.

---

## 3. Project files

```
EmoEarth/
├── app.py                      Flask server (run this to open the app)
├── build_assets.py             Prepares frames, music and timeline for the globe
├── orchestra.py                The orchestra: instruments, harmony, emotion and reverb
├── update_data.py              Checks NASA GIBS for new days and rebuilds what changed
├── export_wave.py              Exports the music's sound wave as CSV / pandas tables
├── auth.py                     Sign-in accounts: python auth.py add NAME / remove NAME / list
├── applog.py                   The app log (logs/emoearth.log); python applog.py errors shows problems
├── signins.py                  Records every sign-in (signins.csv) and counts them for /stats
├── users.json                  Accounts (password hashes only; not in git; made by auth.py)
├── narrate.py                  Writes the spoken description for blind listeners (Gemini, with a built-in fallback)
├── narration_json-input.py     Old command name: now just runs narrate.py
├── narration.py                Experimental: Gemini description from the images themselves
├── .env                        Your private API key (not in git; you create it from .env.example)
├── .env.example                Template for .env with no secrets (in git)
├── download_ice.py             Step 1: downloads the images from GIBS
├── download_ocean.py           Ocean layer: downloads the NASA ECCO2 currents frames once (5c)
├── build_ocean.py              Ocean layer: frames, ocean orchestra and timeline (5c)
├── download_co2.py             Carbon dioxide layer: downloads NASA's DYAMOND CO2 frames once (5c)
├── build_co2.py                Carbon dioxide layer: frames, CO2 orchestra and timeline (5c)
├── make_azure_package.py       Makes azure_deploy.zip for hosting (9b)
├── deploy_azure.py             One command to put the latest EmoEarth on Azure (9b)
├── animate_ice.py              Optional: flat 2D animation (matplotlib)
├── animate_ice_music.py        Optional: flat 2D animation with synced music
├── ice_music.py                Optional: generates only the music (WAV)
├── requirements.txt
├── firebase_web_config.json    Firebase web settings (public; the secret key is firebase-service-account.json, not in git)
├── update_log.txt              One line per data update (created automatically)
├── logs/                       emoearth.log (app log) and signins.csv (every sign-in), not in git (8a, 5a)
├── backup_before_orchestra/    The music and data from before the orchestra (v1.0)
├── static/
│   ├── index.html              The 3D globe web page
│   ├── login.html              The sign-in page shown before the globe
│   ├── login_email.html        The email-only sign-in page (/login/email)
│   ├── version.txt             App version shown at the bottom right (edit it when you release)
│   ├── logo/                   NASA and Star Trek logos shown at the top left
│   └── data/                   Created automatically
│       ├── frames/             Gap-filled daily temperature images (WebP, about 340 KB each)
│       ├── music.mp3           The orchestral music, compressed (about 4.4 MB): what the page plays
│       ├── music.wav           The same music uncompressed (about 33 MB): used by export_wave.py
│       ├── timeline.json       Timing, key, tempo, volume, emotion and instrument levels for every day
│       ├── calibration.json    Frozen pitch, tempo and colour ranges
│       ├── stats_cache.json    Cached per-day temperatures and colour shares (makes rebuilds faster)
│       ├── base.jpg            Dim Earth base map
│       ├── borders.png         Country borders (only if GIBS provides it)
│       ├── coastlines.png      Coastlines (only if GIBS provides it)
│       ├── narration.json      The narration text and where it came from (from narrate.py)
│       ├── narration.wav       The narration as speech (only if pyttsx3 is installed)
│       ├── wave_daily.csv      Sound wave per day (from export_wave.py)
│       ├── wave_envelope.csv   Sound wave shape, 100 rows per second (from export_wave.py)
│       ├── ocean/              The ocean layer: frames/, music.mp3, timeline.json, calibration.json (from build_ocean.py)
│       └── co2/                The carbon dioxide layer: frames/, music.mp3, timeline.json, calibration.json (from build_co2.py)
├── Ice Surface Temperature (Day)/   The downloaded daily images
├── Ocean Currents (ECCO2)/          The downloaded ocean frames (not in git)
├── Carbon Dioxide (DYAMOND)/        The downloaded CO2 frames, shrunk to 2048 x 1024 (not in git)
└── outputs/                         Music samples and slides (e.g. EmoEarth_music_mapping.pptx)
```

---

## 4. Step by step

### Step 0. Set up Python (once)

```bash
cd EmoEarth
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

You should see `(.venv)` at the start of the terminal line. Activate the environment again every time you open a new terminal.

For the Gemini narration (packages already in `requirements.txt`), copy `.env.example` to `.env` and put your key after `GEMINI_API_KEY=` (see 5b, "API keys for the team"). Keep the key only in `.env`; it is in `.gitignore`, so it is never committed.

### Step 1. Download the images

```bash
python download_ice.py
```

What it does:
1. Asks GIBS (`GetCapabilities`) which dates the layer has data for, and skips days without data.
2. For each day from 2026-01-01 to 2026-06-01, requests a global equirectangular image (`GetMap`, EPSG:4326, 2000x1000 pixels, PNG).
3. Requests only the temperature layer, with no base map, and puts it on a black background (matches Worldview).
4. Saves each day as `MODIS_Terra_Ice_Surface_Temp_Day_YYYY-MM-DD.png` in the folder `Ice Surface Temperature (Day)`.
5. Skips files that already exist, so you can stop and restart.

Settings at the top of the file: date range, `REGION` (global, arctic, antarctic), `ADD_BASEMAP`, `BLACK_BACKGROUND`, image size.

### Step 2. Filter / clean the images (gap filling)

This happens automatically inside `build_assets.py`.

Why: the satellite scans in narrow strips along its orbit (a "swath"). Between the strips there are gaps with no data, which show up as black diagonal stripes. Near the poles the strips overlap, so gaps are small there.

How the filter works:
1. A pixel that is pure black (all color channels at or below 12 out of 255) is treated as "no data".
2. For each day, the code looks at the same day and the 2 days before and after (`FILL_DAYS = 2`).
3. Each pixel becomes the average of the valid (non-black) pixels from those days.
4. Because the satellite orbit shifts a little each day, a gap today is usually covered on a neighboring day.

Trade-off: each filled picture is a mix of about 5 days, not strictly one day, and colors are averaged rather than true temperature values. Polar night areas have no data at all and stay black.

### Step 3. Estimate temperature from the images

Also inside `build_assets.py`:
1. Each image is split into a northern half (top) and a southern half (bottom).
2. Valid (non-black) pixels are sampled (up to 4000 per half).
3. Each sampled color is matched to the nearest color on the Worldview color bar, which gives a position from 0 to 1, converted to kelvin (223.2 K to 313.2 K).
4. The average per half is the day's temperature for that hemisphere.
5. Missing days are filled by interpolation, then smoothed over 5 days.

The color bar used here is an approximation copied by eye from the Worldview legend, not the official color table.

### Step 4. Compose the music (the EmoEarth orchestra)

Done by `build_assets.py` (function `compose_music`) together with `orchestra.py`. Each day is one musical beat, 4 days make one bar.

#### 4.1 Musical Instruments Selection

For every day the code also measures how much of the globe is in each of the 7 colours of the colour bar
(the same nearest-colour matching as Step 3, on up to 6000 sampled pixels). Each colour drives one section of the orchestra.
The more of a colour there is, compared with how much there usually is, the louder its section plays.

| Colour | Magnitude | Section | What it plays | Feeling |
|---|---|---|---|---|
| Purple | Lowest | Celesta | Glassy bells an octave above the melody | Ice crystals |
| Blue | Very Low | Cellos & Basses | The bass line (southern hemisphere) | Deep, heavy cold |
| Cyan | Low | Harp | Arpeggios of the chord | Flowing meltwater |
| Green | Moderate | Clarinet | A countermelody under the violins | Warm inner voice |
| Yellow | High | Flute | Doubles the melody an octave higher | Light, sunny |
| Orange | Very High | French Horns | Broad sustained chords | Warmth, swelling |
| Red | Highest | Trumpets & Timpani | Fanfares and drums on the first beat of a bar | Heat, alarm |

Always playing, whatever the colours: **Violins** (the melody) and **Violas** (a soft chord bed).

How loud a section is: `level = base + (1 - base) * share`, where `share` is the colour's amount scaled between its
5th and 95th percentile over the data, and `base` is a small minimum (set in `SECTIONS` in `orchestra.py`) so the orchestra never goes silent.
These colour ranges are frozen in `calibration.json` like the pitch ranges, so old days keep the same instrumentation when new data arrives.

#### 4.2 Soundscape Composition

| Music element | What it represents |
|---|---|
| Melody (violins) | Northern hemisphere magnitude where warmer colour produces higher pitch. Two octaves from C4. On beats 1 and 3 it lands on a note of the chord |
| Bass (cellos & basses) | Southern hemisphere magnitude where warmer colour produces higher pitch. Root of the chord on beat 1 |
| Major or minor | Overall trend of both hemispheres. Higher magnitude telemetry plays C major, while lower magnitude telemetry plays C minor |
| Tempo | How fast the visuals are changing over time. From 66 BPM (calm) to 132 BPM (fast change) |
| Crescendo and decrescendo | Volume rises with increasing magnitude |
| Quick two-note run | Added on days with a sharp change |
| Chords | One chord per bar: I - vi - IV - V in major, i - VI - iv - V in minor (with a raised 7th, B natural, on V) |
| Stereo seating | Like a concert stage: violins and harp left, violas and woodwinds centre, cellos, basses and trumpets right |


#### 4.3 Major and minor changes

1. Compute the day-to-day change of each hemisphere's smoothened intensity, scale both to count equally, average them and smooth over 15 days. This is the "net trend".
2. The key switches to C minor when the trend falls below -0.05 and back to C major when it rises above +0.05 (`MODE_HYST` in `build_assets.py`). This small gap stops the key from flickering when the trend hovers around zero.
3. On the day of a key change the orchestra plays a pivot: the G major chord (the dominant, shared by both keys) with a timpani roll and a horn swell, then the tonic chord of the new key.
4. In minor the harp arpeggios fall instead of rise.

#### 4.4 Emotion

Every day gets one of six emotions from two values:

- **Valence** (positive or negative): major or minor, plus how warm it is.
- **Arousal** (calm or excited): how fast the temperature is changing, plus how much red (heat) there is.

| | Calm | Moving | Intense |
|---|---|---|---|
| Major (positive) | Serene | Joyful | Triumphant |
| Minor (negative) | Melancholy | Tense | Urgent |

The emotion changes how the orchestra plays:

| Emotion | Playing style |
|---|---|
| Serene | Smooth legato violins, gentle harp in triplets |
| Joyful | Livelier notes, faster harp |
| Triumphant | Trumpet fanfare and timpani on each bar |
| Melancholy | Long legato notes, slow harp, falling arpeggios |
| Tense | Trembling strings (tremolo), shorter notes, timpani |
| Urgent | Tremolo, repeated trumpet notes, timpani twice a bar |

#### 4.5 Sound generation

No samples or MIDI are used, instruments are synthesized in Python with numpy:
- Bowed strings, woodwinds and brass: wavetables with each instrument's overtone recipe, several slightly detuned players per section and vibrato that fades in after the attack.
- Flute: also a little breath noise.
- Harp: plucked strings whose higher overtones die away faster.
- Celesta: bell-like partials.
- Timpani: drum partials plus a mallet hit.
- A concert-hall reverb (convolution with a 2.4 second decaying impulse) and a soft limiter.

The result is written as a 44.1 kHz, 16-bit stereo WAV file using Python's built-in `wave` module.
The old single-instrument version is kept in `backup_before_orchestra/` and in git history.

### Step 5. Build the files for the globe

```bash
python build_assets.py
```

(`python app.py` does this automatically the first time.) It creates everything in `static/data/`:
filled frames, `music.wav`, `timeline.json` (date, start time, beat length, BPM, key, key changes, volume, temperature, emotion and orchestra section levels for each day), the base map, the borders and the coastlines. It takes a minute or two (a few minutes the first time, because every image is measured once).

### Step 6. Open the app

Create your sign-in account first (once per computer):

```bash
python auth.py add yourname        # asks for a password (at least 8 characters), twice
```

```bash
python app.py
```

Then open **http://127.0.0.1:5000**, sign in, and press **▶** (browsers block sound until you click).

Keep the terminal open while you use the app: closing it or pressing Ctrl+C stops the server and the page goes blank. After changing any Python file, stop the server (Ctrl+C) and run `python app.py` again; changes to `index.html` or `version.txt` only need a browser refresh.

To rebuild after changing settings or images:

```bash
python app.py --rebuild
```

then hard-refresh the browser (Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows).

When you press ▶ from the start, you first hear the spoken description, then the music begins (see 5b).

### Step 7. Make the narration (optional)

```bash
python narrate.py
```

Writes `static/data/narration.json` and, if pyttsx3 works, `static/data/narration.wav`. Without it the page still speaks a description it builds from the data. Run it again after new data arrives so the description covers the newest days. Details in **5b**.

---

## 5. How the 3D page works

- The music file is the master clock. The page reads the audio's current time and shows the matching day.
- When a note starts, the globe shows that day's image. Between notes it blends smoothly to the next day.
- If the music speeds up, the globe speeds up with it.
- Each day's image is wrapped around a sphere (equirectangular texture). A GLSL shader blends two days, draws the temperature over the base map, and draws the borders on top.
- Black pixels in a frame are treated as "no data", so the base map shows through.

### Controls

| Control | Action |
|---|---|
| Layer menu (top of the legend), or keys Z / X / C | Switch layer: Z ice surface temperature, X ocean currents and sea temperature, C carbon dioxide (5c); the change is spoken |
| Drag | Rotate the globe |
| Right-drag or Shift+drag | Slide the Earth left or right on the screen (e.g. out from under a panel) |
| Double-click | Put the Earth back in the centre |
| Drag a panel | Move the info, legend or playback panel anywhere (buttons and sliders still work normally). The browser remembers where you put it |
| Double-click a panel | Put that panel back where it started |
| – / + button on a panel | Minimise the panel to its title, or expand it again (remembered by the browser) |
| Scroll or pinch | Zoom |
| ▶ / ⏸ button or Space | Start or stop music and animation together (from the start, the narration plays first; ⏭ skips it) |
| 🗣 Describe or D | Hear the spoken description; Esc stops it |
| Narration first | Speak the description before the music starts (off by default) |
| Seek bar | Jump to any moment; music and globe move together |
| North pole, South pole, Equator | Jump to a preset view |
| Auto-rotate | Slowly spin the globe (on by default) |
| Base map | Show or hide the dim Earth surface (off by default) |
| Borders | Show or hide country borders (off by default) |
| Coastlines | Show or hide coastlines (on by default) |
| Data opacity | Fade the observation layer |

### What is on the screen

| Where (default) | Panel | Shows |
|---|---|---|
| Top left | Logos | NASA and Star Trek logos (`static/logo/`) |
| Left | Info panel | Current date, the day's **emotion** ("Feeling: Serene"), key, BPM, dynamic marking (pp to ff), crescendo or decrescendo, approximate north and south hemispheres signals, latest data date with a "Check for new data" button, and a small chart of both hemispheres with a moving playhead |
| Top centre | Narration caption | The words being spoken, shown only while the narration plays |
| Top right | Date and time box | Today's date, a live clock, and the country, UTC offset and time zone |
| Right | Legend panel | The layer menu, that layer's colour bar (and source for the ocean layer), the orchestra mixer and the equalizer bars |
| Bottom centre | Playback bar | ▶ / ⏸ (⏭ skips the narration), 🗣 Describe, seek bar, view buttons, layer switches, Narration first and data opacity |
| Bottom right | Version | e.g. "EmoEarth v3.0" (when it was put online; hover for details) |

Every panel can be dragged, and the info, legend and playback panels can be minimised (see Controls).

Local date and time: the date and time box uses the clock and time zone of the computer running the browser. The country comes from the time zone, using a table built from the IANA `zone.tab` and stored in `index.html`.

Music and emotion on the page:
- **Orchestra mixer**: under the color legend, one row per colour with its instrument and a live level bar, so you can see which sections are playing.
- **Equalizer bars**: under the orchestra mixer, 28 frequency bars from deep bass (40 Hz, left) to treble (12 kHz, right), measured live from the music with a Web Audio `AnalyserNode` (it only measures; the sound is not changed). Cellos, basses and timpani move the left bars; flute, celesta and violins the right ones. Bars grow up and down from a glowing centre line (a faded reflection underneath), have rounded ends, and are coloured along the temperature colour bar (purple bass to red treble) tinted by the current emotion. A white dot marks each band's recent peak and falls slowly, and bands hitting a strong peak throw small sparkles that float up and fade. While paused the bars shimmer gently.
- **Mood glow**: a soft atmosphere around the globe takes the emotion's colour (Serene light blue, Joyful gold, Triumphant orange, Melancholy violet, Tense pink, Urgent red) and glows brighter as the music gets louder. The info panel glows in the same colour.
- **Key change**: the key line flashes when the music moves between C major and C minor.
- **Version**: the app version is shown at the bottom right. It is read from `static/version.txt`, so change that one line when you release (see Change log).

---

## 5a. Sign-in page

Before the globe, EmoEarth shows a sign-in page (`static/login.html`). People can come in four ways:

| Way | How | Set up in |
|---|---|---|
| Name and password | local accounts made with `python auth.py add NAME` | this section |
| Email and password, or Google | Firebase (used automatically when the Firebase files are present) | "Sign-in with Firebase" below |
| **Guest Only** button | one click, no account | "Guest Only" below |
| Email only | the separate page `/login/email` | "Email-only sign-in page" below |

Every sign-in is recorded and counted on `/stats` ("Sign-in records and /stats" below).

The sign-in page's picture Its picture is NASA's Terra satellite (the one carrying MODIS, the instrument behind the temperature data) circling the Earth on its polar orbit and painting a strip of surface temperature colours as it goes, purple and blue near the cold poles to orange and red near the equator. With "reduce motion" turned on in the operating system, it shows a still picture instead.

How it works:
- **Accounts:** `python auth.py add NAME` creates an account or changes its password, `python auth.py remove NAME` deletes it, `python auth.py list` shows the names. They are stored in `users.json` as password hashes only (never the passwords), and `users.json` is in `.gitignore`, so each computer has its own accounts.
- **Everything is behind the sign-in:** the globe page, the data files (frames, music, timeline) and the API answer only for a signed-in person. The sign-in pages, the logos, `version.txt`, `/api/about` (version and update time) and `/api/clientlog` (browser problem reports) are public.
- **Staying signed in:** without "Keep me signed in for 30 days", the sign-in lasts until the browser is closed. The sign-in cookie is signed with a secret key: `FLASK_SECRET_KEY` from `.env` if you set one, otherwise a random key kept in `.flask_secret` (in `.gitignore`).
- **Guessing protection:** after 5 wrong passwords from one address, that address has to wait 10 minutes.
- **Signing out:** the date and time box in the app shows "Signed in as NAME" with a **Sign out** link.

Note: the sign-in needs `app.py` (Flask), on your computer or on Azure (9b). A copy served as plain files (for example on GitHub Pages) has no server, so it has no sign-in, log or counts; anyone with its address can open it.

### Sign-in with Firebase (email, password reset, Google)

When the two Firebase files below are present, the sign-in page switches to Firebase automatically: people sign in with their email, can reset a forgotten password by email, and can optionally use "Sign in with Google". Passwords are kept by Firebase, never by EmoEarth. Without the files, the local `auth.py` accounts above are used.

**Part A. In the Firebase console (once)**
1. Go to https://console.firebase.google.com, click **Create a project** and give it a name (for example `emoearth`). Google Analytics is not needed.
2. In the left menu open **Security → Authentication** (or type "Authentication" in **Search for products**), click **Get started**, then the **Sign-in method** tab: turn on **Email/Password** and save. For the Google button, also add **Google**: set **Public-facing name for project** to `EmoEarth` (people see it on the Google account screen and in emails), pick a support email and save. The Android SHA-1 note does not apply to this web app.
3. **Authentication → Users → Add user**: add each teammate's email and a starting password. They can change it later with "Forgot password?".
4. **Authentication → Settings → Authorized domains**: check that `localhost` is listed and add `127.0.0.1`. Later, add the real domain where EmoEarth is hosted.
5. **Project settings (gear) → General → Your apps → Web (`</>`)**: register an app (no Hosting needed). Copy the values of `firebaseConfig` into a new file `firebase_web_config.json` in the EmoEarth folder, written as JSON (keys and values in double quotes):
   ```json
   {
     "apiKey": "AIza...",
     "authDomain": "emoearth.firebaseapp.com",
     "projectId": "emoearth",
     "appId": "1:123...:web:abc...",
     "googleSignIn": true
   }
   ```
   `googleSignIn` is optional (shows the Google button). These values are not secret; they identify the project.
6. **Project settings → Service accounts → Generate new private key**: save the downloaded file as `firebase-service-account.json` in the EmoEarth folder. **This file is secret**: it is in `.gitignore`, never commit or email it. Share it with teammates privately, or point to it from `.env` with `FIREBASE_SERVICE_ACCOUNT=path/to/key.json`.
7. Optional (recommended): limit who may enter, in `.env`:
   ```
   FIREBASE_ALLOWED_EMAILS=alice@example.com,bob@example.com
   FIREBASE_ALLOWED_DOMAINS=example.edu
   ```
   With both empty, every account in the Firebase project may sign in (Google sign-in lets any Google user create one, so set a list if Google is on).

**Part B. In the app**
1. `pip install -r requirements.txt` (adds `firebase-admin`).
2. Stop any running `app.py` (Ctrl+C) and start it again: `python app.py`. The console should say `Sign-in: Firebase (emoearth)`.
3. Open http://127.0.0.1:5000. The page now asks for **Email**, and shows **Forgot password?** (and **Sign in with Google** if turned on).
4. Test **Forgot password?**: type an email from step A3 and click it; Firebase sends a reset link (check the spam folder). The email text can be changed in Authentication → Templates.

How it stays safe: the browser signs in with Firebase, then sends a short-lived Firebase ID token to `app.py`, which checks it with `firebase-admin` (signature, not revoked, signed in within the last 10 minutes, on the allow-list) before opening a Flask session. Every 10 minutes the server checks the account again, so disabling or deleting a user in the Firebase console signs them out. The 5-tries / 10-minute guessing limit still applies, and Firebase adds its own.

To go back to local accounts, move `firebase_web_config.json` out of the folder and restart.

**Team computers:** `git pull` brings the code and `firebase_web_config.json`, but never the key. Each developer needs `firebase-service-account.json` sent privately and saved next to `app.py` (on Windows check it is not `...json.json`), then `python -m pip install -r requirements.txt` **inside the venv** (in the VS Code terminal that shows `(venv)`; a separate PowerShell window installs into a different Python), then restart `app.py`. If the page still says "Name" and "No accounts yet", the terminal shows why: `No module named 'firebase_admin'` means the package went into the wrong Python.

**If the key was ever committed or shared by mistake:** in Firebase → Project settings → Service accounts → Manage service account permissions → the `firebase-adminsdk` account → Keys, delete the old key, then Generate new private key, and update every computer and the Azure setting `FIREBASE_SERVICE_ACCOUNT_JSON`.

**Reset emails:** they come from `noreply@emoearth-47fbb.firebaseapp.com` and may land in spam at first. Authentication → Templates lets you set the sender name (EmoEarth), reply-to and wording. A sender like `noreply@emoearth.com` needs your own domain: Templates → edit → Customize domain, then add the DNS records Firebase shows.

### Guest Only

Under the **Sign in** button the main sign-in page has a **Guest Only** button ("Explore the globe and its music without an account"). One click opens the globe straight away: no email, no password. Guests can use everything on the globe, but never `/logs` or `/stats`.
- Each guest visit is recorded in `signins.csv` as `guest <id>` with the method `guest`. The id is a random 8-character code kept in the browser for a year (cookie `emo_guest`), so `/stats` can count different guest browsers, not only visits. No personal details are asked or stored.
- At most 30 guest visits per address every 10 minutes. `GUEST_ACCESS=off` (in `.env` or Azure's Environment variables) turns the button's access off.

### Email-only sign-in page

A second sign-in page, **`/login/email`** (for example http://127.0.0.1:5000/login/email), lets people in with just their email address: no password and no Google account. It has the same design as the main sign-in page and links back to it ("Have a password or a Google account? Sign in here"). The main page no longer links to it (the **Guest Only** button took that place); open it directly by its address.

- **Checking the address:** the email box checks the address while you type and when you leave it: it must have exactly one @, a valid name before it (no spaces, no dot at the start or end, no two dots in a row) and a real-looking domain after it (letters, digits and hyphens, a dot, and a 2 to 24 letter ending such as .com or .my). The message says exactly what is wrong ("The part after the @ needs a dot, like example.com"). Common typos such as `gmial.com` or `hotmail.con` get a clickable "Did you mean bob@gmail.com?". The server checks the same rules again.
- **What it does not check:** that the person owns the address (there is no email sent). Anyone can type any address, so treat these visitors as guests. They can play the globe, but they can never open `/logs` or `/stats`, even if they type an address that is on `LOG_VIEWERS`.
- **Already signed in?** The page still opens, with a box "You're already signed in as ...", a **Go to the globe** button and **Sign out and use another email** (`/logout?to=email`, which signs out and comes back to this page). Signing in again with an email replaces the earlier sign-in.
- **Limits:** at most 15 tries per address every 10 minutes. `EMAIL_ACCESS=off` (in `.env` or Azure's Environment variables) turns the page off; `EMAIL_ACCESS_DOMAINS=school.edu.my,example.com` lets in only those domains.

### Sign-in records and /stats

Every sign-in (Guest Only, email-only, Firebase password, Google, or local account) is written as one line in **`signins.csv`**, next to the app log (`logs/signins.csv` on your computer, `/home/LogFiles/emoearth/signins.csv` on Azure, kept across redeploys): time, email or name, how they signed in, address and browser.

The **`/stats`** page has a **Guest Only** section (guest visits, how many different guest browsers, guests today and in the last 7 days, and the guests' share of all sign-ins; the 30-day chart shows guests in green inside each day's bar). It also counts: total sign-ins, how many different people, today, the last 7 days, how people signed in (email only, password, google.com, local account), who signed in most, a bar for each of the last 30 days, and the latest 50 sign-ins. **`/stats.csv`** downloads every line for Excel. In the terminal: `python signins.py` (it prints a separate line for guests).

**Resetting the counts:** `python signins.py reset` starts again from zero; `python signins.py reset guest "email only"` removes only those kinds (for example test visits) and keeps the rest. It asks you to type `yes`, never deletes anything (the old file is renamed to `signins_backup_<date-time>.csv` next to it) and writes a line to the app log. On Azure the records are separate: to reset them, open Azure's file browser (Web App → Development Tools → Advanced Tools → Go → Debug console → `/home/LogFiles/emoearth`) and rename or delete `signins.csv`. Who may open `/stats`: the same people as `/logs` (`LOG_VIEWERS`; on your own computer any signed-in user except email-only guests).

## 5b. Narration for blind and low-vision listeners

EmoEarth can describe the year's data out loud, so someone who cannot see the globe can still follow it.

### Making the narration

1. Put your Gemini API key in a file called `.env` in the project folder (it is in `.gitignore`, so it never goes to GitHub):

   ```
   GEMINI_API_KEY=your-key-here
   ```

   Never write the key inside a `.py` file. If a key was ever committed to git (it was in earlier versions of `narration.py` and `narration_json-input.py`), revoke it in Google AI Studio and make a new one: removing it from the file does not remove it from the git history on GitHub.
2. Run:

   ```bash
   python narrate.py            # Gemini description (falls back to the built-in one if Gemini fails)
   python narrate.py --local    # built-in description only, no internet needed
   ```

   (`python narration_json-input.py` still works and does the same.)
3. It writes `static/data/narration.json` (the text) and, if `pyttsx3` works on your computer, `static/data/narration.wav` (the speech).

   | Field in `narration.json` | Meaning |
   |---|---|
   | `text` | The description that is spoken |
   | `source` | `gemini` or `local` (the built-in description from the data) |
   | `audio` | `narration.wav`, or `null` when there is no audio file (the browser then reads `text` aloud) |
   | `latest_date` | The newest day the description covers |
   | `timeline_version`, `generated_at` | Which build of the data it was made from, and when |

   Settings at the top of `narrate.py`: `MODEL` (Gemini model), `MAX_WORDS` (length, 60) and `RETRIES` (4).

`narrate.py` never stops with an error. When Gemini is busy ("503 UNAVAILABLE ... high demand" or "429", common at peak times), it waits and tries again: 4 attempts, 3, 6 and 12 seconds apart. A key or model problem (400/401/403/404) is not retried. If Gemini still cannot answer, it keeps an earlier Gemini narration if there is one (and says so), otherwise it uses a description built from `timeline.json`, such as: *"EmoEarth, from 1 January to 8 November 2026. In the north, the frozen surface goes from about minus 20 degrees, warms to 18 degrees in August..."*

### API keys for the team

The real key never goes into git: the repository is on GitHub, and anyone who can see a key there can use it (charges and limits go to its owner). Each developer sets up their own `.env` instead:

1. Copy the template: `cp .env.example .env` (Windows: `copy .env.example .env`).
2. Put a key after `GEMINI_API_KEY=`. Two ways to get one:
   - **Own key (recommended):** each developer creates a free key at https://aistudio.google.com/apikey with their own Google account. Nobody has to share anything, and one person's key can be removed without affecting the others.
   - **Shared team key:** the project owner sends the key privately, through a password manager (for example 1Password or Bitwarden shared vault) or a direct message, never in GitHub, an issue, a commit or a public chat. If it may have leaked, the owner creates a new one and everyone updates their `.env`.
3. Run `python narrate.py`. It should say `Narration (gemini, ...)`.

No key at all is fine too: the app and `narrate.py` still work with the built-in description.

For automatic builds on GitHub (GitHub Actions), store the key as a repository secret (Settings, Secrets and variables, Actions, `GEMINI_API_KEY`); it is then available to the build without being visible in the code.

### How the page plays it

- **Narration first** (off by default; tick it in the playback bar): when you press ▶ from the beginning, the description is spoken first and the music starts when it ends, so the two never play over each other. Press ▶ (shown as ⏭) again to skip straight to the music. The box is off when EmoEarth opens; tick it to hear the description first (the browser remembers that choice, and unticking it again turns it off). 🗣 Describe or the D key plays the narration at any time.
- **🗣 Describe button (or the D key)**: speaks the description at any time. If the music is playing, it keeps going quietly underneath (turned down to 15%) and comes back to full volume afterwards. Press it again or Esc to stop.
- **Caption**: the words are shown at the top of the screen while they are spoken.
- **Always something to say**: the page uses the first one that works: (1) `narration.wav`; (2) the text in `narration.json`, read by the browser's built-in voice; (3) a description the page builds from `timeline.json` itself. So it works even if the narration was never generated or the audio file is missing.

### Screen readers and keyboard

- A hidden live region announces short updates while the music plays, for example "March, feeling tense, C minor.", when the month, the mood or the key changes (at most every 4 seconds, never during the narration).
- The globe has a text description, buttons have labels (the play button says "Play" or "Pause"), and the decorative chart is hidden from screen readers.
- Keyboard: Tab to move between controls (a yellow outline shows where you are), Space to play or pause, D to hear the description, Esc to stop it.
- **Z**, **X** and **C** switch the layer: **Z** ice surface temperature, **X** ocean currents and sea temperature, **C** carbon dioxide. The change is spoken ("Switching to Ocean currents and sea temperature"), and after the page reloads it says where you are ("Ocean currents and sea temperature layer, 2007. Press Space to play, D to hear the description."). Pressing the key of the current layer says "Already on ..."; a layer that is not built yet says "... is not available yet". The words go to screen readers (live region) and are also spoken by the browser's voice. The keys do nothing while typing in a text box, or with Ctrl, Cmd or Alt held, so Cmd+C still copies.

---

## 5c. Data layers: ice surface, ocean currents or carbon dioxide

The menu at the top of the legend panel (or the keys **Z**, **X** and **C**) picks what the globe shows. Each layer has its own frames, its own orchestra and its own dates; the info panel, mood, key, temperatures, chart and narration all follow the chosen layer.

| Layer | Key | Data | Dates | Music |
|---|---|---|---|---|
| **Ice surface temperature (MODIS)** (default) | Z | NASA GIBS, MODIS Terra, daily | 2026, grows with new days | `static/data/music.mp3` |
| **Ocean currents & sea temperature** | X | NASA SVS 3912 "Global Sea Surface Currents and Temperature" (ECCO2 model, MIT/JPL), 345 frames, one per model day | 2007-03-25 to 2008-03-03, a fixed set | its own soft ocean orchestra with its own instruments, `static/data/ocean/music.mp3` |
| **Carbon dioxide (DYAMOND)** | C | NASA SVS 5436 "DYAMOND Global Carbon Dioxide" (GEOS model, Science On a Sphere version of 5196), 196 frames, every 6 hours | 2020-01-15 to 2020-03-03, a fixed set | its own CO2 orchestra (rising CO2 turns minor and louder), `static/data/co2/music.mp3` |

Picking a layer reloads the page with `?layer=ice`, `?layer=ocean` or `?layer=co2`, and the browser remembers the choice. Links can use the same address, for example `http://127.0.0.1:5000/?layer=co2`. A layer that has not been built yet shows "(not built yet)" and cannot be picked.

**Making the ocean layer (once)**
```
python download_ocean.py        # about 345 frames, one per model day (~1 GB download from NASA, a while)
python build_ocean.py           # globe frames, the ocean orchestra and its timeline
```
- `download_ocean.py` reads NASA's frame list (2001 frames, 30 per second of video) and takes the one closest to each model day from the version **without** the colour bar (`.../frames/2048x1024_1x1_30p/orig/`), so nothing is painted onto the globe; the colour bar is drawn in the legend instead. It saves them as JPEG in `Ocean Currents (ECCO2)/` (not in git) and skips frames it already has, so it can be stopped and run again. `--step 2` takes every second day.
- `build_ocean.py` turns each frame into a 1600 x 800 WebP (about 0.5 MB) in `static/data/ocean/frames/`. Grey land and the black sea between current lines become transparent, so the base map shows through (tick **Base map** to see the continents). Fading trails stay partly transparent.
- Temperature: each coloured pixel is matched by its hue to NASA's colour bar (0 °C blue, 10 to 20 °C green, about 25 °C yellow, 32 °C red), then averaged for the northern and southern halves. Like the ice layer it is an estimate from colours, good for trends.
- Music: the ocean has its own **soft, slow orchestra with its own instruments** (style `ocean` in `orchestra.py`), composed from the sea temperatures with the same rules as the ice layer (warming seas lean to C major and crescendo, cooling seas to C minor; each colour of NASA's colour bar drives one section, louder when there is more of that colour):

  | Colour (cold to warm) | Ocean instrument | Plays | Ice layer equivalent |
  |---|---|---|---|
  | Coldest blue (0 °C) | **Glass Harmonica** | glassy, slowly swelling bells above the melody | Celesta |
  | Blue | **Double Basses** (with bass clarinet) | the deep bass, from the southern seas | Cellos & Basses |
  | Teal | **Vibraphone** | slow shimmering arpeggios, with the motor's tremolo | Harp |
  | Green | **Oboe** | the singing countermelody | Clarinet |
  | Yellow-green | **Pan Flute** | breathy, doubles the melody an octave up | Flute |
  | Yellow-orange | **Choir** ("ooh") | soft sustained chords | French Horns |
  | Red (32 °C) | **Steel Pan & Drum** | a gentle steel pan figure in warm seas; an ocean drum wash on key changes | Trumpets & Timpani |

  Always playing: a **solo cello** sings the melody (from the northern seas) instead of violins, over a soft string pad, and a swell of filtered noise like distant waves. It is played gently:
  - slower: 46 to 72 beats per minute (one beat = one model day; the ice layer uses 66 to 132), so the 345 days last about 5 and a half minutes;
  - calm moods only (`OCEAN_AROUSAL = 0.45`): Serene and Melancholy;
  - always legato, no tremolo, quick runs, fanfares or timpani hits; a longer, wetter concert hall (3.8 s);
  - about 4.5 dB quieter than the ice music.

  The orchestra mixer in the legend shows these instrument names when the ocean layer is picked. Settings are at the top of `build_ocean.py` (`OCEAN_STYLE`, `OCEAN_BPM`, `OCEAN_AROUSAL`): `OCEAN_STYLE = "gentle"` plays the ice layer's instruments softly instead, and `python build_ocean.py --lively` gives the ice layer's style exactly. The music has its own frozen calibration (`static/data/ocean/calibration.json`), and per-day temperatures are cached in `static/data/ocean/stats_cache.json`, so re-composing takes 1 to 2 minutes.
- The set is fixed: there is no "Check for new data" for this layer.
- Narration: 🗣 Describe uses a description built from the ocean data. A Gemini narration for this layer can be added later as `static/data/ocean/narration.json`.
- Credit: NASA/Goddard Space Flight Center Scientific Visualization Studio (https://svs.gsfc.nasa.gov/3912); ECCO2 model data from MIT/JPL (scientists Hong Zhang and Dimitris Menemenlis). Shown under the colour bar.

**Size:** the 345 ocean frames add about 170 MB to `static/data` (`FRAME_WIDTH = 1600` in `build_ocean.py`; 2048, NASA's full width, is sharper but about 2.5 times bigger). `make_azure_package.py` includes them automatically (without `ocean/music.wav`); the Azure upload grows by the same amount. If that is too much for the Free plan, use `python download_ocean.py --step 2`.


### The carbon dioxide layer (DYAMOND)

**Carbon dioxide (DYAMOND)** in the layer menu shows NASA's GEOS model of carbon dioxide in the air, 15 January to 3 March 2020 (NASA SVS 5436, the Science On a Sphere version of 5196), one frame every 6 hours (196 frames). NASA's pictures already include the land, snow, ice and ocean, so the base map is not needed; carbon dioxide is drawn as tan, orange and red clouds drifting with the wind (fires, cities and industry, mostly in Africa, South and East Asia). Below about 425 ppm the colour is see-through, so the legend's colour bar fades out on the left.

**Making it (once)**
```
python download_co2.py      # 196 frames, every 6 hours (~4 GB from NASA, shrunk to ~75 MB on disk); --every 12 for fewer
python build_co2.py         # globe frames (2048 x 1024 WebP, ~34 MB), the CO2 orchestra and its timeline
```
- `download_co2.py` reads NASA's frame list (1176 hourly frames, 8192 x 4096 PNG) and the date file `dyamond_timestamps.txt`, takes the frames at 00, 06, 12 and 18 UTC, shrinks each to 2048 x 1024 and saves it as JPEG in `Carbon Dioxide (DYAMOND)/` (not in git). It skips frames it already has. Decoding the 8192 x 4096 pictures needs about 1 GB of memory.
- What is measured: for each frame and hemisphere, the share of the map covered by visible high-CO2 plumes (%), and roughly how high they reach (ppm, 425 to 460, matched to NASA's colour bar by hue). Deserts, snow and ocean are left out. Like the other layers these are estimates from colours, good for trends.
- Info panel: the date and time (UTC), then "North: high-CO2 plumes over 1.6% of the map, plumes ≈ 431 ppm" and the same for the south. The chart shows the plume cover of both hemispheres; it rises and falls every day, because carbon dioxide gathers near the ground at night.
- Music: the ice layer's orchestra and instruments, composed from the plume cover (north = melody, south = bass, the 7 parts of the colour bar = the 7 sections), 52 to 92 beats per minute (one beat = 6 hours, about 2 minutes 15 seconds in all). The key is turned around on purpose: **when carbon dioxide rises the music turns to C minor** (and grows louder), when it falls it turns to C major. Settings are at the top of `build_co2.py` (`CO2_BPM`, `CO2_STYLE`, `CO2_AROUSAL`, `CO2_RISING_IS_MAJOR`); `build_assets.compose_music` has the matching `rising_is_major` option.
- The set is fixed: no "Check for new data". 🗣 Describe uses a description built from the CO2 data.
- Credit: NASA/Goddard Space Flight Center Scientific Visualization Studio (https://svs.gsfc.nasa.gov/5436 and https://svs.gsfc.nasa.gov/5196), GEOS model (DYAMOND), shown under the colour bar.

---

## 6. Optional flat (non-3D) versions

| Script | What it does |
|---|---|
| `animate_ice.py` | Plays the downloaded images as a smooth flat animation with a color bar. Can export GIF or MP4 |
| `ice_music.py` | Only creates `ice_temperature_music.wav` |
| `animate_ice_music.py` | Flat animation with the music playing in sync. Can export an MP4 with sound (needs ffmpeg) |

---

## 6b. Sound wave as data (CSV / pandas)

```bash
python export_wave.py              # daily summary + wave envelope (100 rows per second)
python export_wave.py --rate 50    # coarser envelope
python export_wave.py --raw        # also every audio sample (about 16 million rows, very large)
```

| File (in `static/data/`) | One row per | Columns |
|---|---|---|
| `wave_daily.csv` | day (one beat) | date, start_s, duration_s, bpm, key, key_change, emotion, volume, trend, north_K, south_K, rms, loudness_db, peak, and one `level_...` column per orchestra section |
| `wave_envelope.csv` | 1/100 s of music | time_s, date, min and max (the wave outline), rms_left, rms_right, peak, rms, loudness_db |
| `wave_raw.csv` (`--raw` only) | audio sample | time_s, left, right |

From Python, as DataFrames:

```python
import export_wave
daily, env = export_wave.load()
daily.groupby("emotion")["loudness_db"].mean()
env.plot(x="time_s", y=["min", "max"])
```

Run it again after the music is rebuilt to refresh the files.

---

## 6c. File sizes and speed

The page streams one frame per day while the music plays, so file size decides how smoothly it runs.

| What | Before | Now | How |
|---|---|---|---|
| 313 globe frames | ~316 MB (PNG, ~1 MB each) | ~105 MB (WebP, ~340 KB each) | `FRAME_FORMAT = "webp"`, `FRAME_QUALITY = 88` in `build_assets.py` |
| Music | 33 MB (`music.wav`) | 4.4 MB (`music.mp3`, 192 kbps) | `MP3_KBPS = 192`; needs `lameenc` |
| Second visit | everything downloaded again | frames and music come from the browser's cache | `app.py` caching rule |

Details:
- **No-data areas stay exact.** WebP compresses the colours a little (lossy, quality 88; the speckle looks slightly smoother up close), but the empty (black, no-data) areas are stored as a separate transparency layer that is kept exactly. The globe's shader uses that layer, so empty areas still show the base map cleanly. Temperatures and music are always calculated from the original images in `Ice Surface Temperature (Day)/`, never from these frames, so the compression does not change any numbers.
- **Music timing stays exact.** MP3 encoders add about 25 ms of silence at the start; `build_assets.py` trims the same amount before encoding, so `music.mp3` lines up with `music.wav` to within a fraction of a millisecond.
- **Fallbacks.** Without `lameenc` the build writes only `music.wav` and the page plays that. Set `FRAME_FORMAT = "png"` to go back to PNG frames. Old timelines without `frame_ext` / `music` still work.
- Switching format: the next build writes frames in the new format and deletes the old ones.

Work in the browser (about 60 times a second while the page is open):
- **The small temperature chart** draws its two lines once; after that only the white playhead moves, and only when it has moved a whole pixel.
- **Text and level bars** (date, temperatures, time, seek bar, orchestra levels) are only rewritten when their value changes, not on every frame.
- **Idle mode**: when the music is paused, Auto-rotate is off, the narration is not playing and nobody has touched the page for a second, the globe stops redrawing (except once a second, and whenever something changes: dragging, zooming, seeking, a switch or slider, a newly loaded frame). The paused equalizer shimmer slows to about 15 frames a second. Laptops stay cooler and use less battery when EmoEarth is left open.

---

## 7. Known limits

- Temperatures are estimated from image colors, so they show trends, not exact values.
- The Worldview color bar is approximated.
- Gap filling blends several days, so each frame is not strictly one day.
- Ice surface temperature only exists where there is ice or snow, so most of the globe has no data. Polar night also leaves large empty areas.
- North and south move in opposite seasons (January to June: north warms, south cools), so the combined major or minor choice can hover near zero.
- The flat map is stretched onto a sphere, so detail near the poles looks pinched.
- The web page needs an internet connection to load Three.js and, if used, the border fallback data from the jsdelivr CDN.
- The equalizer bars only move while the music plays through the page (the browser needs the ▶ click to start audio).
- The narration describes the whole year at once, not each day. Gemini's wording changes each time it runs, and it can be wrong about details, so check it before sharing.
- Without `narration.wav` the voice depends on the browser and operating system, so it sounds different on each computer.
- The ocean and carbon dioxide layers are fixed model runs from NASA (2007 to 2008, and January to March 2020); only the ice layer gets new days. Carbon dioxide below about 425 ppm is see-through in NASA's pictures, so the CO2 numbers only describe the visible high plumes.
- Guest Only and the email-only page do not prove who someone is (nothing is emailed), so their sign-ins count browsers and typed addresses, not verified people. "Different guest browsers" counts devices: one person on two devices counts twice.
- On Azure's Free plan the site sleeps when nobody uses it, so the first visit afterwards can take up to a minute.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `externally-managed-environment` when installing | Activate the virtual environment first, then use `python -m pip install ...` |
| `ModuleNotFoundError: build_assets` | `build_assets.py` must be in the same folder as `app.py` |
| Page shows 404 | `index.html` must be inside the `static` folder |
| Globe looks off-center or too large | Use the latest `index.html` and hard-refresh the browser |
| No sound | Click Play (browser needs a click), check volume and output device |
| Picture and sound out of step | Change `AUDIO_OFFSET` at the top of the script in `index.html` |
| Missing days in the animation | Some dates have no data for this layer; the scripts skip them |
| `/stats` or `/logs` says "You can't see ..." | Sign in with your own account (not Guest Only or email only) and make sure your email is in `LOG_VIEWERS` (needed on Azure) |
| The sign-in page goes straight to the globe | You are still signed in; use Sign out, a private window, or `/login/email` (it shows "You're already signed in") |
| Something went wrong and you don't know what | Open `/logs?errors=1` (or run `python applog.py errors`); see section 8a |
| The sign-in page says "No accounts yet" | Run `python auth.py add NAME` on the computer running EmoEarth, then sign in |
| Forgot a password | `python auth.py add NAME` again sets a new one (Firebase mode: "Forgot password?" on the sign-in page) |
| Sign-in page asks for "Name" although Firebase is set up | The app is in local-account mode: `firebase-service-account.json` is missing next to `app.py`, or `firebase-admin` is not installed in the venv. The terminal prints the reason when `app.py` starts (README 5a, Team computers) |
| "... isn't on the EmoEarth list" | Add that email to `FIREBASE_ALLOWED_EMAILS` (`.env` locally, Environment variables on Azure) and restart |
| Azure: "disallowed by policy" when creating | Azure for Students allows only some regions; see README 9b |
| Azure: deploy says "Site failed to start within 10 mins" | Often only the slow first start on the Free plan; check `az webapp log startup show -n emoearth -g emoearth-rg` (README 9b) |
| Azure: Cloud Shell says "File size exceeds 100MB" | Upload from your own computer with the Azure CLI (README 9b step 4) |
| The carbon dioxide layer says "(not built yet)" | Run `python download_co2.py`, then `python build_co2.py`, and reload the page |
| The ocean layer says "(not built yet)" | Run `python download_ocean.py`, then `python build_ocean.py`, and reload the page |
| `download_ocean.py` stops with errors part-way | NASA's server was busy; run it again, it skips frames it already has |
| "Too many wrong passwords" | Wait 10 minutes, or restart `app.py` |
| Page is blank or white | The Flask server is not running. Run `python app.py` in the project folder (with `.venv` active) and keep that terminal open, then refresh |
| Blank page with "403 Forbidden" on port 5000 | On a Mac, AirPlay Receiver also uses port 5000 and answers when Flask is not running. Start Flask, use exactly `http://127.0.0.1:5000` (not `localhost`), or turn off AirPlay Receiver in System Settings → General → AirDrop & Handoff |
| VS Code's built-in browser stays white | It is showing an old empty page. Click its reload button, or open http://127.0.0.1:5000 in Chrome |
| `ModuleNotFoundError: No module named 'flask'` | Activate `.venv`, then `python -m pip install -r requirements.txt` |
| A change to a `.py` file has no effect | Stop the server (Ctrl+C) and run `python app.py` again; Python code is only loaded at start |
| Panels are in odd places | Double-click a panel to put it back in its default place |
| Equalizer bars do not move | Press ▶; they only react while music is playing |
| Narration is silent | Check the computer's volume. The browser needs a click first (▶ or 🗣 Describe). Without `narration.wav` the browser's own voice is used; on some systems it must be enabled in the system speech settings |
| `narrate.py` prints a long red error after "Done" (Windows: `DriverProxy.__del__`, `comtypes`, `KeyError: None`) | A harmless pyttsx3 bug while Python shuts down; the text and `narration.wav` were already saved. Fixed in `narrate.py`, which now exits straight after saving. If you still see it, that computer has an older `narrate.py`: `git pull` first |
| `Gemini attempt 1 failed: 503 UNAVAILABLE ... high demand` | Your key is fine; Google's model is overloaded for a moment. `narrate.py` retries, then keeps the previous Gemini narration or uses the built-in one. Run it again later. If it happens often, try another model in `MODEL` |
| "No GEMINI_API_KEY found" | Each computer needs its own `.env` file in the project folder with `GEMINI_API_KEY=...` (it is not in git, on purpose). On Windows, make sure the file is called `.env` and not `.env.txt` (in Notepad choose "All files" when saving) |
| Narration is the plain built-in one, not Gemini's | `narrate.py` could not reach Gemini (no `.env` key, `google-genai` not installed, or the service was busy). Run `python narrate.py` again; check the message it prints |

---

## 8a. Logs: finding problems

EmoEarth keeps one log of what happened and anything that went wrong (`applog.py`).

| Where | File |
|---|---|
| Your computer | `logs/emoearth.log` in the EmoEarth folder (not in git) |
| Azure | `/home/LogFiles/emoearth/emoearth.log` (kept across redeploys), also in **Monitoring → Log stream** |

The file is kept small (1 MB, then the 5 newest older parts as `emoearth.log.1` ... `.5`). Change the folder with `LOG_DIR`.

**What is recorded** (never passwords, tokens or keys):
- the server starting, and which sign-in mode it uses (Firebase or local accounts), or why Firebase could not start;
- sign-ins (who, how: password or Google, from which address), failed sign-ins, people refused by the allow-list, the 10-minute block after 5 wrong passwords, sign-outs, and accounts signed out because they were removed or disabled;
- **crashes**: any error inside the server is written with its full traceback, and the browser gets a short "Something went wrong on the server" message instead of a blank page;
- every server error answer (5xx), data files that are missing (404 under `static/data/`), and requests slower than 5 seconds;
- data updates from NASA GIBS (`update_data.py`, also still in `update_log.txt`);
- **problems in people's browsers**: script errors (with line and stack), globe frames or music that fail to load, and files that fail to load, with the page, layer, user and browser name. The page sends at most 20 reports per visit, and the server keeps at most 60 per address every 10 minutes.

**Reading it**
- In the browser: **`/logs`** (for example http://127.0.0.1:5000/logs), `/logs?errors=1` for warnings and errors only, `/logs?n=1000` for more lines.
  Who may open it: the emails or names in `LOG_VIEWERS` (in `.env`, or in Azure's Environment variables, for example `LOG_VIEWERS=wee_yip@hotmail.com`). Without `LOG_VIEWERS`, any signed-in user may on your own computer, and nobody may on Azure.
- In the terminal: `python applog.py` (last 50 lines) or `python applog.py errors` (problems only).
- On Azure: **Monitoring → Log stream**, or `az webapp log tail -n emoearth -g emoearth-rg`.

Example lines:
```
2026-11-14 11:40:02  INFO    Signed in: wee_yip@hotmail.com (Firebase, google.com) from 203.0.113.5
2026-11-14 11:41:15  WARNING Browser: [frame] globe frame failed to load  src=/static/data/co2/frames/2020-02-01T06.webp  layer=co2  page=/?layer=co2  user=wee_yip@hotmail.com  browser=Mozilla/5.0 ...
2026-11-14 11:42:30  ERROR   Server error on GET /api/status (user wee_yip@hotmail.com, from 127.0.0.1)
Traceback (most recent call last): ...
```

---

## 9. Live data: when NASA GIBS publishes new images

`update_data.py` keeps the app current.

```bash
python update_data.py              # check once
python update_data.py --every 6    # keep checking every 6 hours
python app.py --auto-update 6      # run the web app and check for new data in the background
```

What it does:
1. Reads the layer's available dates from GIBS (`GetCapabilities`).
2. Downloads days it does not have yet (from `START` in `update_data.py`, up to the newest day, or up to `END` if you set one).
3. Re-downloads the newest 4 days every time (`REFRESH_DAYS`), because near-real-time data can be replaced later. A re-downloaded day only counts as changed if its pixels differ.
4. Rebuilds only the frames affected by new or changed days (a frame depends on the days within 2 days of it), then recomposes the music.
5. Writes `timeline.json` last, so the page never sees a half-built dataset.
6. Appends a line to `update_log.txt` every time it runs.

Keeping old music stable: the pitch and tempo ranges are frozen in `static/data/calibration.json` the first time the music is built (with a 15% margin). New days are scaled against that same range, so notes already composed do not change. Values beyond the range are clipped. The last week of music can still shift slightly, because smoothing uses the days around each day. To reset the ranges: `python app.py --recalibrate`.

Rolling window instead of a growing timeline: set `ROLLING_DAYS = 150` in `build_assets.py` to keep only the last 150 days.

On the page: the info panel shows the latest data date and when it was last checked, with a "Check for new data" button. When new data is ready, a blue "New data through ..." bar appears at the top; click it to refresh and return to about the same moment of the music.

Narration: new data does not rewrite the narration automatically. Run `python narrate.py` after an update so the description includes the newest days (until then the page keeps playing the older description, or builds one from the new data if there is none).

Notes: this layer is daily and arrives with a delay, so "live" means new days appear as NASA publishes them, not minute by minute. The first update after upgrading downloads every day from `START` up to the newest day, which can take a few minutes.

---

## 9b. Hosting on Microsoft Azure (share one web address)

EmoEarth can run on Azure App Service (Linux, Python), so everyone opens one address such as `https://emoearth-xxxx.malaysiawest-01.azurewebsites.net` (the live one: `https://emoearth-awbchng6cce2aufp.malaysiawest-01.azurewebsites.net`) and signs in with Firebase. The data (frames, music, narration) is built on your own computer and uploaded ready-made.

Plans: **Free F1** (1 GB memory, 1 GB storage, 60 CPU minutes a day; fine for testing with a few people) or **Basic B1** (paid, recommended when many people use it). Azure has no automatic spending cap, so set a budget alert under Cost Management.

**1. Make the upload file (on your computer)**
```
python make_azure_package.py
```
It makes `azure_deploy.zip` (about 116 MB) with only what the server needs: the Python files, `firebase_web_config.json`, `static/` (without `music.wav`) and a short `requirements.txt` for the server (Flask, gunicorn, firebase-admin, requests, pillow, numpy, lameenc). It never contains `.env`, the Firebase key, `.flask_secret` or `users.json`. `azure_deploy.zip` is in `.gitignore`.

**2. Create the Web App (portal.azure.com)**
- **Create a resource → Web App** (or App Services → Create → Web App).
- Resource group: new, `emoearth-rg`. Name: `emoearth` (must be unique in Azure). Publish: **Code**. Runtime stack: **Python 3.12**. Operating system: **Linux**. Region: one near your users (for example Southeast Asia or Malaysia West). Leave **Secure unique default hostname** on; the address then gets a random part, like `emoearth-awbchng6cce2aufp.malaysiawest-01.azurewebsites.net`.
- **Azure for Students** subscriptions may only create resources in a few regions (Policy → Assignments → "Allowed resource deployment regions" → Parameters lists them). A "disallowed by policy" error means: pick one of those regions. "Deny - All Resources Creation" means the subscription itself is blocked (check its status and credit, or use a personal Azure account); do not try to delete that policy.
- Pricing plan: create a new plan, choose **Free F1** or **Basic B1**.
- **Review + create → Create**, then **Go to resource**. The address is on the Overview page (Default domain).

**3. Settings (the secrets live here, not in the zip)**
- **Settings → Environment variables → App settings → + Add**, one at a time, then **Apply**:

  | Name | Value |
  |---|---|
  | `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` (Azure installs the packages) |
  | `FLASK_SECRET_KEY` | a long random text: `python -c "import secrets; print(secrets.token_hex(32))"` |
  | `FIREBASE_SERVICE_ACCOUNT_JSON` | the whole contents of `firebase-service-account.json`, from `{` to `}` (Mac: `cat firebase-service-account.json | pbcopy`, then paste) |
  | `FIREBASE_ALLOWED_EMAILS` | who may sign in, comma-separated, for example `wee_yip@hotmail.com,ptonn1998@gmail.com` (no quotes) |
  | `FIREBASE_ALLOWED_DOMAINS` | optional: everyone with an email at these domains, for example `student.university.edu.my` |
  | `LOG_VIEWERS` | who may open `/logs` and `/stats`, for example `wee_yip@hotmail.com` (8a) |
  | `GUEST_ACCESS` | optional: `off` turns the Guest Only button off (5a) |
  | `EMAIL_ACCESS` / `EMAIL_ACCESS_DOMAINS` | optional: `off` turns the email-only page off, or limit it to some domains (5a) |

- Click the main **Apply** at the bottom of the page, then **Confirm** (nothing is saved before that).
- **Startup command**: **Settings → Configuration → Stack settings** tab (older portals: General settings) →
  `gunicorn --bind=0.0.0.0 --timeout 600 --workers 1 --threads 4 app:app`
  and turn **HTTPS Only** on (General settings tab). **Save**. If the box is hard to find, use the Azure CLI instead:
  `az webapp config set -g emoearth-rg -n emoearth --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 --workers 1 --threads 4 app:app"` and `az webapp update -g emoearth-rg -n emoearth --https-only true`. (One worker, because the sign-in guessing limit and the update status live in memory.)

**4. Upload the zip** from your own computer with the Azure CLI (Cloud Shell's upload stops at 100 MB, and the zip is bigger):
- Install it once: Mac `brew install azure-cli`; Windows `winget install -e --id Microsoft.AzureCLI` (then open a new terminal).
- `az login` (a browser window opens; sign in with the account that owns the Web App).
- In the EmoEarth folder: `az webapp deploy --resource-group emoearth-rg --name emoearth --src-path azure_deploy.zip --type zip`
- It takes 5 to 10 minutes (Azure installs the packages). On the Free plan the first start can be slower than the command waits for, so it may end with "Site failed to start within 10 mins" although the site starts a little later. Check with `az webapp log startup show -n emoearth -g emoearth-rg`: "Site started" near the end means it is running. If not, `az webapp log tail -n emoearth -g emoearth-rg` shows the error.

**5. Firebase**: Security → Authentication → Settings → Authorized domains → **Add domain**: the Default domain from step 2 (without `https://`).

**6. Open the address.** The sign-in page should ask for Email (the first visit after a quiet spell takes up to a minute on the Free plan).

**7. Letting people in.** Each person needs (a) their email in `FIREBASE_ALLOWED_EMAILS` (or their domain in `FIREBASE_ALLOWED_DOMAINS`) in Azure's Environment variables, then Apply → Confirm, and (b) a way to sign in: **Sign in with Google** (nothing to set up), or an email/password account made in Firebase → Authentication → Users → Add user (they can change the password with "Forgot password?"). "... isn't on the EmoEarth list" means (a) is missing; the account still appears in Firebase → Users, because Firebase creates it before EmoEarth checks the list. To remove someone, take them off the list and disable or delete them in Firebase → Users.

**One-command update (recommended):** after any change to the code or the data, run
```
python deploy_azure.py
```
It checks the Azure CLI is installed and signed in (and opens `az login` if not), lists what changed since your last upload (new, changed and removed files; it stops if nothing changed), checks the Python files compile so a typo never goes online, makes `azure_deploy.zip`, uploads it, then waits until the site answers with the new build number (up to 15 minutes, because the Free plan can be slow to start) and prints the address. It remembers each upload in `.deploy_state.json` (not in git) and writes a line to the app log.
- `python deploy_azure.py --check` only lists what changed, without uploading.
- `python deploy_azure.py --force` uploads even when nothing changed.
- Another Web App or resource group: set `AZURE_WEBAPP` and `AZURE_RESOURCE_GROUP` in `.env`.
- The first run on a computer uploads everything, because there is no record of an earlier upload yet.
- If it says the site did not answer in time, look at `az webapp log tail -n emoearth -g emoearth-rg` (or Monitoring → Log stream), fix, and run it again.

**Updating the site by hand** (`git push` only updates GitHub, not Azure):
```
python make_azure_package.py
az webapp deploy --resource-group emoearth-rg --name emoearth --src-path azure_deploy.zip --type zip
```
The settings in Azure (keys, allow-list, startup command) stay. Build new data on your computer first. A new Python package needed by the web app goes into `SERVER_REQUIREMENTS` in `make_azure_package.py`, a new code file it imports into `CODE` there. To change the plan later (for example Free F1 to Basic B1): Web App → **Scale up (App Service plan)**; the app, settings and address stay.

If the page shows an error, open **Monitoring → Log stream** in Azure: `Firebase could not start (...)` usually means the key was not pasted completely.

**When was it set up?** Every package made by `make_azure_package.py` carries a small `build_info.json` (version from `static/version.txt`, the time the package was made, the git commit, and a build number); the script prints it, for example `Build 20261114115637 (v3.0, made 2026-11-14T11:56:37+08:00, git 5e9a01d)`. People see it on the site:
- bottom right of the globe page and under the sign-in form: **"EmoEarth v3.0 · updated 14 Nov 2026, 11:56"** (hover the globe page's label for where it runs, the git commit and the build number);
- while the page is open, it checks every 5 minutes; when a newer version has been put online, a blue badge says **"EmoEarth has been updated (...) – click to reload"**;
- `/api/about` gives the same as JSON (`version`, `packaged_at`, `git`, `build`, `started_at` = when the server last started, `host`);
- the log records it at every start: `EmoEarth app loaded: v3.0, build 20261114115637 (packaged ...)`.
On your own computer (no `build_info.json`) the label says "running since" with the time `app.py` started.

Notes: the server keeps the files from the zip; "Check for new data" on Azure downloads and rebuilds on the server and uses a lot of the Free plan's CPU minutes, so it is better to build on your computer and upload a new zip. On Azure the sign-in cookie is sent over HTTPS only.

## 10. Change log

Newest first. Add a line here for every update.

How to release: change `static/version.txt` (for example to `v1.2`), rename the "Unreleased" heading below to that version and date, commit, and push.

### Unreleased (2026-11-14 to 2026-11-15): Panels, equalizer, narration, sign-in, Azure, ocean and CO2 layers, logs and sign-in counts
- Each panel (info, legend and orchestra, playback bar) has a – button in its top-right corner that minimises it to its title; + expands it again. The browser remembers the choice.
- Right-drag or Shift+drag slides the Earth left or right on the screen; double-click re-centres it. Normal drag still rotates.
- New date and time box in the top-right corner: date, live clock, country, UTC offset and time zone.
- Default panel layout: info panel at the left edge, legend panel at the right edge below the clock, playback bar at the bottom centre.
- Panels can be dragged anywhere on the screen; double-click a panel to put it back. Positions are remembered, and panels stay on screen when the window is resized.
- Live equalizer bars (frequency analyser) under the orchestra mixer: mirrored rounded bars in the temperature colours tinted by the mood, falling peak dots and sparkles.
- New `export_wave.py`: exports the music's sound wave as `wave_daily.csv` (per day) and `wave_envelope.csv` (100 rows per second), or as pandas DataFrames.
- `requirements.txt` now includes Flask.
- README: full file list, "What is on the screen" table, how to release, and troubleshooting for blank pages, port 5000 / AirPlay and restarting the server.
- README: new Flask section (install, addresses, `app.py` options) and a table of what each Python package is used for.
- Narration for blind and low-vision listeners: new `narrate.py` (Gemini, with a description built from the data when Gemini is unavailable), narration played before the music or on demand with the music turned down, captions, screen-reader announcements and keyboard shortcuts (D, Esc).
- Security: the Gemini API key was removed from `narration.py` and `narration_json-input.py`; it is now read from a private `.env` file (in `.gitignore`).
- New default view: Auto-rotate and Coastlines on, Base map and Borders off.
- Faster loading: globe frames are WebP instead of PNG (316 MB to 105 MB, no-data areas kept exact), the page plays a compressed `music.mp3` (33 MB to 4.4 MB, timing kept exact), and the browser now keeps frames and music between visits. New setting `FRAME_FORMAT`, `FRAME_QUALITY`, `MP3_KBPS`; new package `lameenc`.
- Lighter page: the temperature chart is drawn once and only its playhead moves, text and level bars update only when they change, and the globe stops redrawing when paused and idle.
- `narrate.py` no longer prints a long pyttsx3 error on exit (Windows).
- `narrate.py`: longer retries when Gemini is busy (503/429), no pointless retries for key or model errors, and an earlier Gemini narration is kept instead of being replaced by the plain one.
- New `.env.example` template (in git, no secrets) and README instructions for giving each developer an API key safely.
- `narrate.py`: each Gemini attempt now gives up after 60 seconds (`TIMEOUT_S`) instead of hanging, and the script exits cleanly on Windows.
- `requirements.txt` now lists every package the project uses, grouped and commented: google-genai, pyttsx3, sounddevice and opencv-python added.
- Sign-in page (`static/login.html`) before the globe: Terra satellite painting a temperature swath; accounts with `auth.py` (hashed passwords in `users.json`), everything behind the sign-in, "keep me signed in for 30 days", a 10-minute wait after 5 wrong passwords, and a Sign out link in the app.
- Optional sign-in with Firebase Authentication: email and password, "Forgot password?" reset emails, optional Google sign-in and an email/domain allow-list. Turns on automatically when `firebase_web_config.json` and the service account key are present; otherwise local accounts are used. New package `firebase-admin`; the key file is in `.gitignore`. Step-by-step setup in section 5a.
- Hosting on Microsoft Azure (README 9b): new `make_azure_package.py` builds `azure_deploy.zip` with only the server files and a short server package list (adds gunicorn); the Firebase key can be given as the app setting `FIREBASE_SERVICE_ACCOUNT_JSON`; the sign-in cookie is HTTPS-only on Azure.
- Azure guide tested end to end: student-subscription region limits, startup command under Stack settings (or with the Azure CLI), upload with the Azure CLI (Cloud Shell stops at 100 MB), slow first start on the Free plan, the allow-list for each user, and how to update the site after a change. EmoEarth now runs at `https://emoearth-awbchng6cce2aufp.malaysiawest-01.azurewebsites.net`.
- `app.py` no longer stops when the Firebase key setting is pasted incompletely; it prints the reason and falls back to local accounts.
- README: team computers and Firebase (key not in git, install inside the venv), replacing a leaked key, password-reset email sender, and new troubleshooting rows.
- `requirements.txt`: added `gunicorn` (the web server used on Azure).
- "Narration first" is now off by default: ▶ starts the music straight away. Tick it to hear the description first (remembered per browser); 🗣 Describe / D still plays it any time.
- New data layer menu in the legend: **Ocean currents & sea temperature** (NASA SVS 3912, ECCO2 model, 2007-03-25 to 2008-03-03) next to the MODIS ice layer. New `download_ocean.py` (one frame per model day from NASA's frames without the colour bar) and `build_ocean.py` (transparent-background WebP frames, temperatures from NASA's colour bar, a separate ocean orchestra and timeline in `static/data/ocean/`). The info panel, mood, key, chart, legend colours, equalizer colours and description follow the chosen layer; the fixed ocean set has no "Check for new data". README 5c.
- The ocean layer now has its own soft, slow orchestra (`orchestra.compose(style="gentle")`): 46 to 72 BPM, calm moods, legato strings, slow harp, no fanfares or drum hits, longer hall reverb, distant waves, quieter. `build_assets.compose_music` takes optional tempo, calmness and style settings; the ice layer's music is unchanged. `build_ocean.py --lively` gives the old style; per-day ocean temperatures are cached.
- The ocean orchestra now has its own instruments (`orchestra.py` style "ocean", `OCEAN_SECTIONS`): Glass Harmonica, Double Basses with bass clarinet, Vibraphone, Oboe, Pan Flute, Choir and Steel Pan & Drum, with a solo cello melody and distant waves. The legend's mixer shows them on the ocean layer.
- New data layer **Carbon dioxide (DYAMOND)** (NASA SVS 5436, GEOS model, 15 Jan to 3 Mar 2020, every 6 hours): new `download_co2.py` and `build_co2.py`, plume cover and ppm estimated from NASA's colour bar, its own orchestra (rising CO2 sounds minor and louder: new `rising_is_major` option in `build_assets.compose_music`), time of day in the info panel, CO2 colour bar and credit in the legend. The layer menu now greys out any layer that is not built yet. README 5c.
- Sign-in page text now describes all three layers (ice surface, ocean currents and sea temperature, carbon dioxide) instead of the ice layer only.
- The `Claude outputs/` folder is now `outputs/` (music samples and slides).
- New app log (`applog.py`, README 8a): sign-ins and failed sign-ins, server crashes with full tracebacks, server errors, missing data files, slow requests, data updates, and problems reported by people's browsers (script errors, frames or music that fail to load). Read it at `/logs` (allowed users: `LOG_VIEWERS`), with `python applog.py errors`, or in Azure's Log stream. Frames that fail to load are tried again after 10 seconds.
- Browsers now keep the ocean and carbon dioxide frames and music between visits too (long cache for every layer).
- People can see when EmoEarth was set up: `make_azure_package.py` stamps each package with `build_info.json`; the globe and sign-in pages show "EmoEarth v3.0 · updated <date, time>", the globe page offers a reload when a newer version goes online (checked every 5 minutes), and `/api/about` returns the details (README 9b).
- New `deploy_azure.py`: one command to update Azure after a change (lists what changed, checks the code compiles, packages, uploads, waits until the new build is live, remembers the upload). `make_azure_package.py` now has `files_to_ship()`, writes the zip safely (`.tmp` first) and leaves out `.DS_Store` and half-written files.
- Layer hotkeys for blind and low-vision listeners: **Z** ice surface temperature, **X** ocean currents and sea temperature, **C** carbon dioxide, with a spoken confirmation and, after the switch, a spoken "where you are" (README 5b, Screen readers and keyboard).
- New email-only sign-in page `/login/email` (same design, email check while typing with typo suggestions, same rules on the server, `EMAIL_ACCESS` / `EMAIL_ACCESS_DOMAINS` settings); the main sign-in page links to it. Every sign-in is now recorded in `signins.csv` and counted on the new `/stats` page (total, different people, per day, by method, latest) with a CSV download (README 5a). The email-only page opens even when you are already signed in, and offers "Go to the globe" or "Sign out and use another email".
- The main sign-in page's "Continue with email only" link is replaced by a **Guest Only** button that opens the globe straight away (new `/login/guest`; guests are recorded as `guest <id>` and counted on `/stats`; `GUEST_ACCESS=off` turns it off). The email-only page stays at `/login/email`.
- `/stats` and `python signins.py` now count Guest Only visits on their own: guest visits, different guest browsers, today, last 7 days, share of all sign-ins, and guests per day.
- `python signins.py reset [kinds...]` resets the sign-in counts (all, or only e.g. `guest` and `email only`), keeping a backup copy.

### v1.1 (2026-11-14): Orchestra and emotion
- New `orchestra.py`: the music is now a synthesized orchestra (violins, violas, cellos & basses, celesta, harp, clarinet, flute, French horns, trumpets & timpani).
- Each of the 7 map colours drives one section; its loudness follows how much of that colour is on the globe that day.
- Major and minor changes now use a small threshold (no flickering) and are marked by a pivot chord, a timpani roll and a horn swell.
- Each day has an emotion (Serene, Joyful, Triumphant, Melancholy, Tense, Urgent) that shapes how the orchestra plays.
- Page: emotion label, orchestra mixer under the legend, mood-coloured glow around the globe, flash on key changes.
- `timeline.json` gained `emotion`, `inst`, `instruments` and `key_change`. `stats_cache.json` gained the colour shares (`b`), and `calibration.json` gained `band_lo` and `band_hi`.
- After updating, run `python app.py --rebuild` once (or `python build_assets.py`). The first build re-reads every image to measure the colours, so it takes a few minutes.
- The previous music is kept in `backup_before_orchestra/`.

### v1.0 (2026-11-14): Version label
- The app version is shown at the bottom right of the page and read from `static/version.txt`.
