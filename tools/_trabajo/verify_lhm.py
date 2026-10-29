import urllib.request, hashlib, json, os

# Download LibreHardwareMonitor.zip (the .NET Framework build)
url = 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'
target = 'C:/Users/Torta/Desktop/LibreHardwareMonitor.zip'

print(f'Downloading from: {url}')
urllib.request.urlretrieve(url, target)
print('Downloaded')

# Calculate SHA-256
sha256 = hashlib.sha256()
with open(target, 'rb') as f:
    for chunk in iter(lambda: f.read(8192), b''):
        sha256.update(chunk)

calculated = sha256.hexdigest()
print(f'Calculated SHA-256: {calculated}')

# Expected digest from GitHub API
expected = 'sha256:086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'
expected_hash = expected.split(':')[1] if ':' in expected else expected
print(f'Expected SHA-256:   {expected_hash}')
print(f'Match: {calculated == expected_hash}')