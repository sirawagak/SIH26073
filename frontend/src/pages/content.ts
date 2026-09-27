/**
 * Static presentation copy, ported verbatim from the original dashboard/index.html.
 * No content was invented; every string here existed in the previous dashboard.
 */
export interface StaticPage {
  id: string; eyebrow: string; h1: string; lede: string[];
  h2: string[]; cards: { h3: string; p: string }[]; paras: string[];
}

export const PAGES: Record<string, StaticPage> = {
  "home": {
    "id": "home",
    "eyebrow": "SIH 26073 · Ministry of Earth Sciences · India Meteorological Department",
    "h1": "What counts as normaldepends on where and when.",
    "lede": [
      "Temperature changes with the place and the time. Delhi can be 12 °C at 4 AM in winter and 25 °C the same afternoon, and another location can be completely different at that same hour. So we cannot say 25 °C is always normal, or always abnormal.",
      "The system learns what temperature is normally expected at that time and season, and flags any reading that suddenly does not fit the pattern."
    ],
    "h2": [],
    "cards": [
      {
        "h3": "Physics first",
        "p": "That's what we mean by \"Physics first\" — use basic physical laws to remove obviously impossible data before using AI."
      },
      {
        "h3": "Compare against normal",
        "p": "The basic idea is that we first check whether the sensor readings are physically possible. For example, the dew point can never be higher than the actual air temperature. So if the air temperature is 25 °C but the sensor says the dew point is 30 °C, we know immediately that something is wrong with the reading.We don't need AI or any complicated model to detect this. We can simply use basic physics rules to catch these impossible values.So, before sending the data to our ML model, we first do these simple physics-based checks. If a value is physically impossible, we flag it as a bad or faulty sensor reading. If it passes the physics check, then we can use the ML model to look for more subtle abnormalities."
      },
      {
        "h3": "It runs inside the station",
        "p": "The main idea is that we compare every reading with what it should normally have been, rather than using one fixed limit for everything."
      }
    ],
    "paras": [
      "That's what we mean by \"Physics first\" — use basic physical laws to remove obviously impossible data before using AI.",
      "The basic idea is that we first check whether the sensor readings are physically possible. For example, the dew point can never be higher than the actual air temperature. So if the air temperature is 25 °C but the sensor says the dew point is 30 °C, we know immediately that something is wrong with the reading.We don't need AI or any complicated model to detect this. We can simply use basic physics rules to catch these impossible values.So, before sending the data to our ML model, we first do these simple physics-based checks. If a value is physically impossible, we flag it as a bad or faulty sensor reading. If it passes the physics check, then we can use the ML model to look for more subtle abnormalities.",
      "The main idea is that we compare every reading with what it should normally have been, rather than using one fixed limit for everything.",
      "The basic idea here is that weather has patterns. For example, during the day the temperature is usually higher, at night it becomes cooler. Similarly, summers are hotter and winters are colder.So instead of using one fixed limit for the temperature, we first teach the computer what the normal pattern looks like. Then, whenever we get a new sensor reading, we compare it with what we would normally expect at that particular time.For example, 25 °C is a completely normal temperature in Delhi. But if the sensor says it is 25 °C at 4 AM in January, that is unusual because normally the temperature should be much lower. So instead of simply asking, \"Is 25 °C too high?\", our system asks, \"Is 25 °C normal for 4 AM in January?\"Suppose the expected temperature is 11 °C, but the sensor reports 25 °C. The difference is 14 °C. That difference is called the deviation from the normal pattern. If the difference is small, we consider the reading normal. If the difference is very large, we suspect that something may be wrong with the sensor.",
      "Keep the detector small enough to run inside the station, and only communicate when something is wrong. This makes the station more energy-efficient and helps it run longer on solar power.",
      "The main idea here is that our detection system is very small and lightweight. It only needs around nine important values or parameters to make its decision, so it doesn't require a powerful computer. Because it is so small, we can actually run the detector inside the weather station itself.Normally, the station has to send its sensor data to another system using a radio connection. But the radio consumes a lot of battery power.So instead, the station first checks its own readings locally. Most of the time, everything is normal, so the radio doesn't need to turn on. If the detector finds something unusual, then the station switches on the radio and sends an alert or the relevant data to us.This saves a lot of energy because the radio is only being used when there is actually something important to report."
    ]
  },
  "problem": {
    "id": "problem",
    "eyebrow": "01 · why the obvious answer fails",
    "h1": "A limit catches nothingand shouts at everything.",
    "lede": [
      "Finding a weird number is easy. Anyone can do that. The hard part is knowing whether the weather changed or the sensor broke. Both look like \"a weird number.\""
    ],
    "h2": [
      "So the real question is not \"is this reading strange\""
    ],
    "cards": [
      {
        "h3": "01 — Slow sensor drift",
        "p": "A faulty sensor doesn't always fail suddenly. It can slowly drift away from the actual temperature: 20°C → 21°C → 22°C → 23°C → 24°C. Every reading looks reasonable on its own, so a simple fixed limit might never detect the problem."
      },
      {
        "h3": "02 — Real weather events",
        "p": "SkyGuard compares the reading with the normal pattern over time to identify gradual changes."
      },
      {
        "h3": "The thing that separates them",
        "p": "A sudden temperature change doesn't always mean the sensor is broken. For example: 25°C → 26°C → 27°C → 35°C. A simple threshold might immediately flag 35°C as a sensor failure, but the change could be caused by a genuine weather event such as a dust storm."
      }
    ],
    "paras": [
      "A simple temperature limit doesn't work because a faulty sensor can slowly drift without crossing the limit, while a real weather event can cross the limit and be wrongly identified as a sensor failure.",
      "A faulty sensor doesn't always fail suddenly. It can slowly drift away from the actual temperature: 20°C → 21°C → 22°C → 23°C → 24°C. Every reading looks reasonable on its own, so a simple fixed limit might never detect the problem.",
      "SkyGuard compares the reading with the normal pattern over time to identify gradual changes.",
      "A sudden temperature change doesn't always mean the sensor is broken. For example: 25°C → 26°C → 27°C → 35°C. A simple threshold might immediately flag 35°C as a sensor failure, but the change could be caused by a genuine weather event such as a dust storm.",
      "SkyGuard uses the surrounding data and learned weather patterns to distinguish a real environmental change from a faulty sensor.",
      "Real weather is connected. When a front passes, temperature, pressure and humidity all move together in a combination thermodynamics permits. A rotting temperature sensor moves alone while the other two carry on normally. Counting how many channels moved, and whether the combination makes physical sense, is the whole trick.",
      "Three lines: dark blue (temperature), purple (humidity), teal (pressure). They travel along flat, then all three bend at the same place, then settle again. They react together. That is real weather.",
      "The red line rises and wanders off on its own. Purple and teal stay flat and never react, because nothing actually happened outside. The one that moved alone is the one that is lying."
    ]
  },
  "faults": {
    "id": "faults",
    "eyebrow": "02 · what breaking looks like",
    "h1": "Seven shapes.",
    "lede": [
      "Each fault leaves a distinct signature in the trace. Recognise the shape and you can name the cause, which is what an engineer actually needs to hear."
    ],
    "h2": [],
    "cards": [],
    "paras": [
      "The last two are missing from the official problem statement, which lists only spikes, frozen values and communication errors. Step offsets and rising noise are both common and both worth adding — it shows the panel you thought past the question as written."
    ]
  },
  "how": {
    "id": "how",
    "eyebrow": "03 · the design",
    "h1": "Cheap check first.Expensive check last.",
    "lede": [
      "Four steps, each costlier than the last, each running less often. Like a clinic: nurse at the door, doctor next, specialist only if needed."
    ],
    "h2": [],
    "cards": [
      {
        "h3": "The 16 features",
        "p": "Three variables — temperature, pressure, humidity — become sixteen columns: gap-aware steps, 24-hour rolling spread, the reading minus its local median, a day-of-year × hour-of-day climatology z-score, and sine/cosine of hour and day. The raw readings themselves were removed: they drift with the season, and the model was scoring October as broken simply because October is cooler than June."
      },
      {
        "h3": "Why climatology, not a limit",
        "p": "42 °C is an ordinary May afternoon in Delhi and impossible in January. A single global limit either misses winter faults or drowns in summer false alarms. The climatology feature asks a better question: how far is this reading from what this hour, on this day of the year, normally looks like?"
      },
      {
        "h3": "Why the forest cannot see a frozen sensor",
        "p": "An Isolation Forest finds points that are easy to separate — the extremes. A stuck sensor produces the opposite: a step of exactly zero, which sits at the 49th percentile, the densest part of the distribution. Measured recall on stuck-at faults was 0.00. A fifteen-line rule that counts repeated values catches them all. Knowing which tool to stop using is part of the design."
      },
      {
        "h3": "Why the threshold moves",
        "p": "Anomaly scores drift upward across the year even after the seasonal features are removed. A threshold fixed in January fired on 31 % of October. Taking a trailing 30-day quantile instead holds the alert rate near its budget and cut false positives by 64 % — the single largest improvement in the whole project, and it came from calibration, not from a bigger model."
      },
      {
        "h3": "What this page is actually running",
        "p": "The live page streams a simulated station into the real frozen model over HTTP. Feature engineering, the Isolation Forest, the adaptive threshold and the stuck-sensor rule all execute server-side in Python — the browser only draws what comes back. If the API is unreachable the page falls back to a transparent in-browser rule set, and says so in plain words. There is no trained Random Forest in this project, and nothing here classifies faults with a learned model."
      }
    ],
    "paras": [
      "Three variables — temperature, pressure, humidity — become sixteen columns: gap-aware steps, 24-hour rolling spread, the reading minus its local median, a day-of-year × hour-of-day climatology z-score, and sine/cosine of hour and day. The raw readings themselves were removed: they drift with the season, and the model was scoring October as broken simply because October is cooler than June.",
      "42 °C is an ordinary May afternoon in Delhi and impossible in January. A single global limit either misses winter faults or drowns in summer false alarms. The climatology feature asks a better question: how far is this reading from what this hour, on this day of the year, normally looks like?",
      "An Isolation Forest finds points that are easy to separate — the extremes. A stuck sensor produces the opposite: a step of exactly zero, which sits at the 49th percentile, the densest part of the distribution. Measured recall on stuck-at faults was 0.00. A fifteen-line rule that counts repeated values catches them all. Knowing which tool to stop using is part of the design.",
      "Anomaly scores drift upward across the year even after the seasonal features are removed. A threshold fixed in January fired on 31 % of October. Taking a trailing 30-day quantile instead holds the alert rate near its budget and cut false positives by 64 % — the single largest improvement in the whole project, and it came from calibration, not from a bigger model.",
      "The live page streams a simulated station into the real frozen model over HTTP. Feature engineering, the Isolation Forest, the adaptive threshold and the stuck-sensor rule all execute server-side in Python — the browser only draws what comes back. If the API is unreachable the page falls back to a transparent in-browser rule set, and says so in plain words. There is no trained Random Forest in this project, and nothing here classifies faults with a learned model."
    ]
  },
  "plan": {
    "id": "plan",
    "eyebrow": "05 · execution",
    "h1": "Ten days, one freeze.",
    "lede": [],
    "h2": [
      "Built and working",
      "Not built yet",
      "Where the marks are"
    ],
    "cards": [
      {
        "h3": "What we do not claim",
        "p": "Listed as future work, not as features."
      }
    ],
    "paras": [
      "Listed as future work, not as features.",
      "Innovation outweighs accuracy. And real-time, scalability, deployability and energy together are worth double the accuracy marks — which is exactly where a heavy deep-learning entry loses.",
      "No trained Random Forest, no fault classifier, no accuracy figure for naming faults. The model is a binary detector: anomaly or not. Fault names other than “stuck value” are heuristic labels applied after the fact and were never evaluated, so the interface calls them likely faults. Detection itself was measured on injected faults only — one station, one year, one seed."
    ]
  }
};

export const FAULT_CARDS = [
  {
    "k": "spike",
    "n": "Spike",
    "d": "One reading leaps far away and comes straight back. Loose wiring or electrical interference.",
    "c": "Point fault"
  },
  {
    "k": "step",
    "n": "Step offset",
    "d": "The level jumps once and simply stays there. Follows a recalibration, a board swap or a power event.",
    "c": "Not in the brief"
  },
  {
    "k": "drift",
    "n": "Drift",
    "d": "Creeps further from the truth every day while every single reading still looks plausible. The dangerous one.",
    "c": "Point fault"
  },
  {
    "k": "stuck",
    "n": "Stuck value",
    "d": "The same number repeats for hours while the other sensors keep moving. Frozen logger or dead element.",
    "c": "Collective fault"
  },
  {
    "k": "noise",
    "n": "Rising noise",
    "d": "Average stays right but the spread grows. A connection is going bad — usually months before total failure.",
    "c": "Not in the brief"
  },
  {
    "k": "dropout",
    "n": "Dropout",
    "d": "Nothing arrives at all. Points at the radio or the power supply rather than the sensor itself.",
    "c": "Comms fault"
  },
  {
    "k": "physics",
    "n": "Impossible reading",
    "d": "Dew point above air temperature, or humidity past 100%. No model needed — the data simply cannot be true.",
    "c": "Physics gate"
  },
  {
    "k": "storm",
    "n": "Genuine weather",
    "d": "All three move together in a physically sensible combination. This must never raise an alarm.",
    "c": "Keep quiet"
  }
];

export const PIPELINE = [
  {
    "title": "1 · Feature engineering",
    "sub": "16 stationary features"
  },
  {
    "title": "2 · Isolation Forest",
    "sub": "200 trees, unsupervised"
  },
  {
    "title": "3 · Adaptive threshold",
    "sub": "Trailing 30-day quantile"
  },
  {
    "title": "4 · Anomaly result",
    "sub": "Score, threshold, detector"
  }
];

export const TIMELINE = [
  {
    "d": "DONE",
    "w": "Dataset, parsing, cleaning and EDA"
  },
  {
    "d": "DONE",
    "w": "Feature engineering — 16 stationary features"
  },
  {
    "d": "DONE",
    "w": "Synthetic fault injection, 5 labelled classes"
  },
  {
    "d": "DONE",
    "w": "Isolation Forest, 200 trees, unsupervised"
  },
  {
    "d": "DONE",
    "w": "Hybrid detector with the stuck-sensor rule"
  },
  {
    "d": "DONE",
    "w": "Adaptive rolling-quantile threshold"
  },
  {
    "d": "DONE",
    "w": "Frozen inference module, parity-verified"
  },
  {
    "d": "DONE",
    "w": "FastAPI service — /health and /predict"
  },
  {
    "d": "FROZEN",
    "w": "Dashboard integrated with the live model"
  },
  {
    "d": "FUTURE",
    "w": "SHAP explainability"
  },
  {
    "d": "FUTURE",
    "w": "Regression residual features"
  },
  {
    "d": "FUTURE",
    "w": "Causal real-time features"
  },
  {
    "d": "FUTURE",
    "w": "Multi-station scaling"
  },
  {
    "d": "FUTURE",
    "w": "ESP32 / edge deployment"
  }
];

export const RUBRIC = [
  {
    "label": "Innovation & novelty",
    "points": 25,
    "strength": true
  },
  {
    "label": "Detection accuracy",
    "points": 20,
    "strength": false
  },
  {
    "label": "Real-time capability",
    "points": 15,
    "strength": true
  },
  {
    "label": "Explainability",
    "points": 10,
    "strength": false
  },
  {
    "label": "Scalability",
    "points": 10,
    "strength": true
  },
  {
    "label": "Practical deployability",
    "points": 10,
    "strength": true
  },
  {
    "label": "Visualisation / UI",
    "points": 5,
    "strength": false
  },
  {
    "label": "Energy efficiency",
    "points": 5,
    "strength": true
  }
];
