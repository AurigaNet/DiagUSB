import urllib.request, json

u = urllib.request.urlopen('https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest')
d = json.loads(u.read())

for a in d['assets']:
    name = a.get('name', '')
    size = a.get('size', '')
    digest = a.get('digest', '')
    url = a.get('browser_download_url', '')
    print('Name:', name, 'Size:', size, 'Digest:', digest[:20] if digest else '', 'URL:', url[:80] if url else '')