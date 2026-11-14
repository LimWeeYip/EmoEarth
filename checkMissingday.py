import requests
import xml.etree.ElementTree as ET

LAYER = "AIRS_L3_Surface_Air_Temperature_Daily_Day"
url = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetCapabilities"
root = ET.fromstring(requests.get(url, timeout=60).content)
ns = {"w": "http://www.opengis.net/wms"}

for layer in root.iter("{http://www.opengis.net/wms}Layer"):
    name = layer.find("w:Name", ns)
    if name is not None and name.text == LAYER:
        dim = layer.find("w:Dimension", ns)
        print("找到图层:", LAYER)
        print("时间范围:", dim.text if dim is not None else "无")
        break
else:
    print("没找到该图层，换一个名字试试")