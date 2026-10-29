import urllib.request, json

u = urllib.request.urlopen('https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest')
d = json.loads(u.read())

for a in d['assets']:
    print('=== Asset ===')
    for k, v in a.items():
        print(f'  {k}: {v}')
    print()