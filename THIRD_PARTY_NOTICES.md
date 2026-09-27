# Third-party notices

Surya Saarthi uses the data, fonts, icons and code listed below. The same list, in short form, is on the site's **Privacy & Disclaimer** page (`#/credits`).

## Data

| What | Source | Licence / terms |
|---|---|---|
| Solar irradiance and forecast | [Weather data by Open-Meteo.com](https://open-meteo.com/) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Free API, for non-commercial use. Attribution is shown in the landing and dashboard footers. |
| Grid CO₂ factor (0.71 kg/kWh) | CEA CO₂ Baseline Database for the Indian Power Sector, v21.0 | Published by the Central Electricity Authority, Government of India |
| Recorded weather for the benchmark (`backend/data/weather_delhi.json`) | Open-Meteo Historical Weather API (ERA5 reanalysis) and Previous Runs API (day-ahead forecasts) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), weather data by Open-Meteo.com |
| Solar model defaults (14% system losses, 96% inverter efficiency) | NREL PVWatts default values | Published parameters, used as assumptions |

## AI model

`openai/gpt-oss-20b` by OpenAI (Apache License 2.0), served through the Groq API under Groq's terms.

## Fonts (bundled through Fontsource, SIL Open Font License 1.1)

- **Space Grotesk**: Copyright 2020 The Space Grotesk Project Authors (https://github.com/floriankarsten/space-grotesk)
- **Inter**: Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)
- **JetBrains Mono**: Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)

These Font Software are licensed under the SIL Open Font License, Version 1.1. The full licence text is at https://openfontlicense.org and in each package's `LICENSE` file (`frontend/node_modules/@fontsource-variable/*/LICENSE`).

## Icons

**Lucide** (`lucide-react`), ISC License.
Copyright (c) 2026 Lucide Icons and Contributors. Parts derived from Feather, Copyright (c) 2013-present Cole Bemis (MIT).

## Adapted components (from 21st.dev)

### Wave Background: `frontend/src/components/ui/wave-background.jsx`

By Kain Xu (https://21st.dev/@xubohuah/components/wave-background), inspired by Antoine Wodniack. Adapted for this project.

```
MIT License

Copyright (c) Kain Xu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### WebGL Shader: `frontend/src/components/ui/web-gl-shader.jsx`
### Liquid Glass Button: `frontend/src/components/ui/liquid-glass-button.jsx`

By Ali Imam (https://21st.dev/@designali-in), published on 21st.dev for copy-and-use. The author's 21st.dev pages list the licence as "unknown", and neither component appears in the author's public GitHub repositories. Credited here and in each file's header; adapted for this project.

## Open-source packages

**Frontend:** React, React DOM, Tailwind CSS, tw-animate-css, shadcn/ui, Base UI, Radix UI (dialog, slot, tooltip, separator), three.js, simplex-noise, clsx, tailwind-merge: MIT. class-variance-authority: Apache-2.0. Vite, oxlint: MIT.

**Backend:** FastAPI, Pydantic, LangGraph, LangChain Core, langchain-groq: MIT. Uvicorn, python-dotenv: BSD-3-Clause. groq (Python SDK), Requests: Apache-2.0. SciPy: BSD-3-Clause (bundles the HiGHS linear/MILP solver, MIT). NumPy: BSD-3-Clause (with bundled components under 0BSD, MIT, Zlib, CC0-1.0).

Each package's own licence file is in `frontend/node_modules/<package>/` or the installed Python package metadata.
