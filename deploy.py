import paramiko, time, re
import sys
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8','replace').strip()
    err = stderr.read().decode('utf-8','replace').strip()
    return out, err

def clean(s):
    return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)

files = [
    ("app.py",                  "/home/uniwai11/physics_tutor/app.py"),
    ("frontend/index.html",     "/home/uniwai11/physics_tutor/frontend/index.html"),
    ("frontend/main.js",        "/home/uniwai11/physics_tutor/frontend/main.js"),
    ("core/wav2lip_lipsync.py", "/home/uniwai11/physics_tutor/core/wav2lip_lipsync.py"),
    ("core/llm.py",             "/home/uniwai11/physics_tutor/core/llm.py"),
]

sftp = client.open_sftp()
print("Uploading files...")
for local, server in files:
    sftp.put(local, server)
    pod_path = server.replace("/home/uniwai11", "/workspace")
    out, err = run(f"kubectl cp {server} {POD}:{pod_path}")
    ok = "OK" if not err or "slurm" in err else f"ERR: {err[:50]}"
    print(f"  {local}: {ok}")
sftp.close()

# Check ollama pull progress
print("\n=== Ollama pull progress ===")
out, _ = run(f"kubectl exec {POD} -- tail -2 /tmp/pull.log 2>&1")
print(clean(out))

# Check if model ready
print("\n=== Ollama models ===")
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    names = [m['name'] for m in data.get('models', [])]\n"
    "    print('Models:', names)\n"
    "except Exception as e: print('Error:', e)\n"
    "\""
)
print(out)

# Verify new code in pod
print("\n=== Verify new code ===")
out, _ = run(f"kubectl exec {POD} -- grep -c 'video_saved' /workspace/physics_tutor/app.py 2>&1")
print("video_saved in app.py:", out)
out, _ = run(f"kubectl exec {POD} -- grep -c 'saved-video' /workspace/physics_tutor/frontend/index.html 2>&1")
print("saved-video in index.html:", out)

print("\nUpload complete!")
client.close()
