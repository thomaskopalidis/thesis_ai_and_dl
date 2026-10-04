import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('10.255.11.254', username='uniwai11', password='GbypPRuuyds', timeout=30)
def run(cmd, timeout=300):
    s, o, e = client.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8','replace').strip(), e.read().decode('utf-8','replace').strip()
POD = 'physics-tutor-74b5558965-gj6qm'

out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, os\n"
    "base = 'https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc'\n"
    "dest = '/workspace/SadTalker/checkpoints/'\n"
    "files = ['auido2exp_00300-model.pth', 'auido2pose_00140-model.pth', 'facevid2vid_00189-model.pth.tar', 'shape_predictor_68_face_landmarks.dat']\n"
    "for f in files:\n"
    "    p = dest + f\n"
    "    if os.path.exists(p) and os.path.getsize(p) > 1000:\n"
    "        print('Skip:', f)\n"
    "        continue\n"
    "    print('Download:', f)\n"
    "    try:\n"
    "        urllib.request.urlretrieve(base + '/' + f, p)\n"
    "        print('  OK', os.path.getsize(p))\n"
    "    except Exception as e:\n"
    "        print('  FAIL:', e)\n"
    "print('done')\n"
    "\""
)
print(out[-600:] or err[-200:])
client.close()
