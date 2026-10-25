# downloads some coco images into data/samples and builds the test zips
import urllib.request
import zipfile
from pathlib import Path

COCO_IDS = [39769, 139, 285, 632, 724, 776, 785, 802, 872, 885, 1000, 1268, 1296, 1353, 1425, 1490, 1503, 1532, 1584, 1675, 1761, 1818, 1993, 2006, 2149]

root = Path(__file__).resolve().parent.parent / "data"
samples = root / "samples"
samples.mkdir(parents=True, exist_ok=True)

files = []
for cid in COCO_IDS:
    dst = samples / f"coco_{cid:012d}.jpg"
    if not dst.exists():
        try:
            dst.write_bytes(urllib.request.urlopen(f"http://images.cocodataset.org/val2017/{cid:012d}.jpg", timeout=20).read())
        except Exception as e:
            print(f"skip {cid}: {e}")
            continue
    files.append(dst)
print(f"{len(files)} sample images in {samples}")


def make_zip(name, members):
    with zipfile.ZipFile(root / name, "w", zipfile.ZIP_STORED) as z:
        for arc, data in members:
            z.writestr(arc, data)
    print(f"wrote {root / name} ({len(members)} entries)")


make_zip("bulk_small.zip", [(f.name, f.read_bytes()) for f in files[:10]])
make_zip("bulk_large.zip", [(f"run{r}/{f.name}", f.read_bytes()) for r in range(3) for f in files])

# messy zip: junk files, a truncated jpeg and a fake png to test error handling
broken = files[0].read_bytes()[:2000]
junk = [("photos/nested/" + files[5].name, files[5].read_bytes()), ("README.txt", b"not an image"), ("broken.jpg", broken), ("fake.png", b"this is text pretending to be a png"), ("__MACOSX/._" + files[0].name, b"\x00\x05\x16\x07"), (".DS_Store", b"\x00")]
make_zip("bulk_messy.zip", [(f.name, f.read_bytes()) for f in files[:5]] + junk)
