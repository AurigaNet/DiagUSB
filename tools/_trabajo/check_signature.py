import subprocess

result = subprocess.run(
    ['powershell', '-Command', 'Get-AuthenticodeSignature "C:/Users/Torta/Desktop/PawnIO_setup.exe"'],
    capture_output=True, text=True
)
print('STDOUT:')
print(result.stdout)
print('STDERR:')
print(result.stderr)
print('Return code:', result.returncode)