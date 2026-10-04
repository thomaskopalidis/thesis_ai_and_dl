import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('10.255.11.254', username='uniwai11', password='GbypPRuuyds', timeout=30)
def run(cmd, timeout=20):
    s, o, e = client.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8','replace').strip(), e.read().decode('utf-8','replace').strip()
POD = "physics-tutor-74b5558965-gj6qm"

# Test various URLs from pod
tests = [
    ("pypi.org", "https://pypi.org"),
    ("ollama.com", "https://ollama.com"),
    ("huggingface.co", "https://huggingface.co"),
    ("registry.ollama.ai", "https://registry.ollama.ai"),
]
for name, url in tests:
    out, err = run(
        f"kubectl exec {POD} -- python3 -c \""
        f"import urllib.request\n"
        f"try:\n"
        f"    r = urllib.request.urlopen('{url}', timeout=5)\n"
        f"    print('OK', r.status)\n"
        f"except Exception as e: print('FAIL:', str(e)[:60])\n"
        f"\""
    )
    print(f"{name}: {out or err[:80]}")

client.close()
