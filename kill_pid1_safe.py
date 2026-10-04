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

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

def clean(s):
    return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)

print("Verifying /tmp will survive restart...")
out, _ = run(f"kubectl exec {POD} -- ls /tmp/bin/ollama 2>&1")
print("/tmp/bin/ollama:", out)
out, _ = run(f"kubectl exec {POD} -- ls /tmp/ollama_models/manifests/ 2>&1")
print("/tmp/ollama_models:", out[:100])

print("\nKilling PID 1 (container will restart, /tmp survives)...")
run(f"kubectl exec {POD} -- kill 1 2>&1", timeout=5)

print("Waiting for container restart...")
time.sleep(8)

# Wait for app to be back up
for i in range(30):
    out, _ = run(f"kubectl logs {POD} --tail=3 2>&1")
    if "Uvicorn running" in out or "Application startup complete" in out:
        print(f"  App UP after {i*3}s!")
        break
    if i % 3 == 0:
        print(f"  [{i*3}s] {out[-60:].strip()}")
    time.sleep(3)

time.sleep(5)

print("\nFull startup log:")
out, _ = run(f"kubectl logs {POD} --tail=25 2>&1")
print(out)

print("\nChecking wav2lip works now:")
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import sys\n"
    "sys.path.insert(0, '/tmp/.local/lib/python3.10/site-packages')\n"
    "sys.path.insert(0, '/workspace/physics_tutor')\n"
    "from core.wav2lip_lipsync import generate_wav2lip_video\n"
    "import librosa\n"
    "print('librosa', librosa.__version__, '- wav2lip import OK')\n"
    "\""
)
print(out)

client.close()
