import paramiko, re
import sys
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

def clean(s):
    return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)

print("=== Ollama pull progress ===")
out, _ = run(f"kubectl exec {POD} -- tail -2 /tmp/pull.log 2>&1")
print(clean(out))

print("\n=== Ollama models available ===")
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    names = [m['name'] for m in data.get('models', [])]\n"
    "    print('Models:', names if names else 'None yet')\n"
    "except Exception as e: print('Ollama offline:', e)\n"
    "\""
)
print(out)

print("\n=== App log (last 10 lines) ===")
out, _ = run(f"kubectl logs {POD} --tail=10 2>&1")
print(out)

print("\n=== New code in pod ===")
out, _ = run(f"kubectl exec {POD} -- grep -c 'video_saved' /workspace/physics_tutor/app.py 2>&1")
print("video_saved code:", "YES" if out.strip() == "1" else "NO")

client.close()
