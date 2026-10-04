"""Install SadTalker in pod and download checkpoints."""
import paramiko, time, sys
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

# Check if SadTalker is already cloned
out, _ = run(f"kubectl exec {POD} -- ls /workspace/SadTalker 2>&1")
print("SadTalker dir:", out[:100])

if "No such file" in out:
    print("\nCloning SadTalker...")
    out, err = run(
        f"kubectl exec {POD} -- git clone --depth=1 "
        "https://github.com/OpenTalker/SadTalker.git /workspace/SadTalker 2>&1",
        timeout=120
    )
    print(out[-200:] or err[-200:])
else:
    print("SadTalker already cloned.")

# Install SadTalker deps
print("\nInstalling SadTalker Python deps...")
out, err = run(
    "kubectl exec " + POD + " -- python3 -m pip install -q --user "
    "face_alignment==1.3.5 imageio imageio-ffmpeg yacs pydub kornia einops "
    "scikit-image basicsr facexlib gfpgan 2>&1",
    timeout=180
)
print(out[-300:] or err[-300:])

# Download SadTalker checkpoints
print("\nDownloading SadTalker checkpoints (~1.5GB)...")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import subprocess, os\n"
    "os.makedirs('/workspace/SadTalker/checkpoints', exist_ok=True)\n"
    "os.makedirs('/workspace/SadTalker/gfpgan/weights', exist_ok=True)\n"
    "# Download main checkpoint\n"
    "base = 'https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc'\n"
    "files = [\n"
    "    ('SadTalker_V0.0.2_256.safetensors', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('SadTalker_V0.0.2_512.safetensors', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('mapping_00109-model.pth.tar', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('mapping_00229-model.pth.tar', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('auido2exp_00300-model.pth', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('auido2pose_00140-model.pth', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('facevid2vid_00189-model.pth.tar', '/workspace/SadTalker/checkpoints/'),\n"
    "    ('shape_predictor_68_face_landmarks.dat', '/workspace/SadTalker/checkpoints/'),\n"
    "]\n"
    "import urllib.request\n"
    "for fname, dest in files:\n"
    "    path = dest + fname\n"
    "    if os.path.exists(path) and os.path.getsize(path) > 1000:\n"
    "        print('Skip:', fname)\n"
    "        continue\n"
    "    print('Downloading:', fname)\n"
    "    try:\n"
    "        urllib.request.urlretrieve(base + '/' + fname, path)\n"
    "        print('  OK:', os.path.getsize(path))\n"
    "    except Exception as e:\n"
    "        print('  FAIL:', e)\n"
    "print('Done')\n"
    "\"",
    timeout=600
)
print(out[-500:] or err[-300:])

# Download GFPGAN weights
print("\nDownloading GFPGAN weights...")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, os\n"
    "dest = '/workspace/SadTalker/gfpgan/weights/'\n"
    "os.makedirs(dest, exist_ok=True)\n"
    "files = [\n"
    "    ('https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth', dest),\n"
    "    ('https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth', dest),\n"
    "    ('https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth', dest),\n"
    "    ('https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth', dest),\n"
    "]\n"
    "for url, d in files:\n"
    "    fname = url.split('/')[-1]\n"
    "    path = d + fname\n"
    "    if os.path.exists(path) and os.path.getsize(path) > 1000:\n"
    "        print('Skip:', fname)\n"
    "        continue\n"
    "    print('Downloading:', fname)\n"
    "    try:\n"
    "        urllib.request.urlretrieve(url, path)\n"
    "        print('  OK:', os.path.getsize(path))\n"
    "    except Exception as e:\n"
    "        print('  FAIL:', e)\n"
    "print('Done')\n"
    "\"",
    timeout=300
)
print(out[-300:] or err[-200:])

# Check what we have
print("\nCheckpoints downloaded:")
out, _ = run(f"kubectl exec {POD} -- ls -lh /workspace/SadTalker/checkpoints/ 2>&1")
print(out)

client.close()
print("\nSadTalker setup complete.")
