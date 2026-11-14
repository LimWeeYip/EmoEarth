# 🌍 EmoEarth: NASA Earth Data as a 3D Globe with Music 



## 1. Data Sources
| Item | Source |
|---|---|
| Temperature imagery | NASA GIBS (Global Imagery Browse Services), layer `MODIS_Terra_Ice_Surface_Temp_Day` (Terra / MODIS, v6.1 STD) |
| How it is fetched | GIBS WMS service (`https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi`), no API key needed |
| Browse the same layer | NASA Worldview (https://worldview.earthdata.nasa.gov) |
| Base map (optional) | GIBS layer `BlueMarble_NextGeneration` |
| Country borders | GIBS layer `DoS_International_Boundaries` (U.S. Department of State) if available as an image; otherwise Natural Earth country borders via the `world-atlas` package on the jsdelivr CDN |
| Coastlines | GIBS layer `Coastlines_15m` if available as an image; otherwise land outlines from Natural Earth (`world-atlas` on the jsdelivr CDN) |
| Color scale | 223.2 K to 313.2 K (about -50 °C to 40 °C) |
| Ocean layer (optional) | NASA/GSFC Scientific Visualization Studio 3912, "Global Sea Surface Currents and Temperature": ECCO2 model (MIT/JPL), 2007-03-25 to 2008-03-03, frames from https://svs.gsfc.nasa.gov/vis/a000000/a003900/a003912/frames/2048x1024_1x1_30p/ (see 5c) |
| Ocean colour scale | 0 °C (blue) to 32 °C (red), NASA's colour bar `sst_ecco2_cbar.png` |
| Carbon dioxide layer (optional) | NASA/GSFC Scientific Visualization Studio 5436, "DYAMOND Global Carbon Dioxide" (Science On a Sphere version of 5196): NASA GEOS model, 2020-01-14 to 2020-03-03, hourly frames from https://svs.gsfc.nasa.gov/vis/a000000/a005400/a005436/frames/8192x4096_2x1_30p/soscomp_1-29-2025a_pngs/ (see 5c) |
| Carbon dioxide colour scale | 380 to 460 ppm (`dyamondCbar_6-27-2024a.png`); see-through below about 425 ppm, then tan, orange and red |

## 2. Project Files
## 3. Methodology
- Fetch the frames (download and try first) -> Next step, use API
- Processing of Frames
- Mapping visuals to sound

  
## 5. Sonification
## 6. UI UX
