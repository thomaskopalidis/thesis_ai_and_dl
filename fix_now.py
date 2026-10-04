"""Upload fixed wav2lip_lipsync.py and start Ollama (small model for quick test)."""
import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)
sftp = client.open_sftp()

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

# 1. Upload fixed wav2lip_lipsync.py
print("Uploading wav2lip_lipsync.py...")
sftp.put(
    r"c:\Users\thoma\Desktop\AI and DL\Thesis_ai_and_dl\core\wav2lip_lipsync.py",
    "/home/uniwai11/wav2lip_lipsync.py"
)
run("kubectl cp /home/uniwai11/wav2lip_lipsync.py " + POD + ":/workspace/physics_tutor/core/wav2lip_lipsync.py")
print("  OK")
sftp.close()

# 2. Verify the env fix is in
out, _ = run("kubectl exec " + POD + " -- grep -n 'PYTHONPATH' /workspace/physics_tutor/core/wav2lip_lipsync.py 2>&1")
print("PYTHONPATH fix:", out)

# 3. Download Ollama binary
print("\nDownloading Ollama binary...")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, os, stat\n"
    "os.makedirs('/tmp/bin', exist_ok=True)\n"
    "url = 'https://github.com/ollama/ollama/releases/download/v0.6.5/ollama-linux-amd64'\n"
    "urllib.request.urlretrieve(url, '/tmp/bin/ollama')\n"
    "os.chmod('/tmp/bin/ollama', stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP)\n"
    "print('DONE', os.path.getsize('/tmp/bin/ollama'))\n"
    "\"",
    timeout=300
)
print("Binary:", out or err[:200])

if "DONE" not in out:
    print("Binary download failed!")
    client.close()
    sys.exit(1)

# 4. Start Ollama
print("\nStarting Ollama server...")
run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import subprocess, os\n"
    "env = dict(os.environ)\n"
    "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
    "env['HOME'] = '/tmp'\n"
    "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
    "os.makedirs('/tmp/ollama_models', exist_ok=True)\n"
    "p = subprocess.Popen(['/tmp/bin/ollama', 'serve'],\n"
    "    env=env, stdout=open('/tmp/ollama.log','w'), stderr=subprocess.STDOUT)\n"
    "print('PID:', p.pid)\n"
    "\"",
    timeout=10
)
time.sleep(8)

# 5. Check server
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    models = [m['name'] for m in data.get('models', [])]\n"
    "    print('UP models:', models)\n"
    "except Exception as e: print('DOWN:', e)\n"
    "\""
)
print("Ollama:", out)

if "DOWN" in out or not out:
    print("Ollama log:")
    out2, _ = run("kubectl exec " + POD + " -- tail -10 /tmp/ollama.log 2>&1")
    print(out2)
    client.close()
    sys.exit(1)

# 6. Pull small model for quick test
if "qwen" not in out.lower():
    print("\nPulling qwen2.5:3b (~2GB, ~3 min)...")
    run(
        "kubectl exec " + POD + " -- python3 -c \""
        "import subprocess, os\n"
        "env = dict(os.environ)\n"
        "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
        "env['HOME'] = '/tmp'\n"
        "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
        "p = subprocess.Popen(['/tmp/bin/ollama', 'pull', 'qwen2.5:3b'],\n"
        "    env=env, stdout=open('/tmp/pull.log','w'), stderr=subprocess.STDOUT)\n"
        "print('Pull PID:', p.pid)\n"
        "\"",
        timeout=10
    )
    import re
    def clean(s): return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)
    print("Monitoring pull...")
    for i in range(40):
        time.sleep(15)
        out, _ = run("kubectl exec " + POD + " -- tail -1 /tmp/pull.log 2>&1")
        pct = clean(out)
        print(f"  [{(i+1)*15}s] {pct[:80]}")
        if "success" in pct.lower():
            print("  DONE!")
            break
else:
    print("Model already available!")

print("\nAll done. Test the app in browser.")
client.close()
