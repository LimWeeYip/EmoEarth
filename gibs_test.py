import requests

url = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
params = {
    "version": "1.3.0", "service": "WMS", "request": "GetMap",
    "layers": "MODIS_Terra_CorrectedReflectance_TrueColor",
    "styles": "", "format": "image/jpeg", "crs": "EPSG:4326",
    "bbox": "-90,-180,90,180",   
    "width": 1200, "height": 600, "time": "2021-09-21",
}

r = requests.get(url, params=params, timeout=30)
r.raise_for_status()


if "image" not in r.headers.get("Content-Type", ""):
    print(r.text)
else:
    with open("earth.jpg", "wb") as f:
        f.write(r.content)
    print("Earth.jpg")