import argparse, json, subprocess, cv2, os, glob
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
import numpy as np
from multiprocessing import Pool, cpu_count
import torch
import torch.nn as nn
import random
from torchvision.models import resnet18
WORKER_MODEL = None
def init_worker(model_path):
    """Initializer for each pool worker: build & load model once per worker."""
    global WORKER_MODEL
    # Make torch single-threaded inside worker
    torch.set_num_threads(1)
    # Build model architecture
    model = build_resnet18_6ch()
    # Load weights onto CPU to avoid GPU driver issues and extra memory
    state = torch.load(model_path, map_location="cpu")
    model.load_state_dict(state)
    model.eval()
    WORKER_MODEL = model

def exif_read(path):
    out = subprocess.check_output(["exiftool", "-j", "-n", path], text=True)
    meta = json.loads(out)[0]

    # Helper to get either "X" or "X " or "X Y" variants
    def g(*keys, default=None):
        for k in keys:
            if k in meta:
                return meta[k]
        return default

    # Parse Dewarp Data e.g. "YYYY-mm-dd; fx,fy,cx,cy,k1,k2,p1,p2,k3"
    dewarp = g("DewarpData", "Dewarp Data")
    fx=fy=cx=cy=k1=k2=p1=p2=k3=None
    if isinstance(dewarp, str) and ";" in dewarp:
        _, nums = dewarp.split(";", 1)
        vals = [float(x.strip()) for x in nums.replace("\n", " ").split(",") if x.strip()!=""]
        if len(vals) >= 9:
            fx, fy, cx, cy, k1, k2, p1, p2, k3 = vals[:9]

    # Vignetting coefficients k[0..5]
    vign = g("VignettingData", "Vignetting Data")
    kpoly = None
    if isinstance(vign, str):
        kpoly = [float(x.strip()) for x in vign.split(",") if x.strip()!=""]
        if len(kpoly) < 6:
            kpoly = None

    # Calibrated HMatrix: 9 numbers
    hcal = g("CalibratedHMatrix", "Calibrated HMatrix")
    H = None
    if isinstance(hcal, str):
        hvals = [float(x.strip()) for x in hcal.split(",") if x.strip()!=""]
        if len(hvals) == 9:
            H = np.array(hvals, dtype=np.float64).reshape(3,3)

    h_dewarp = g("DewarpHMatrix", "Dewarp HMatrix" )
    H_d = None 
    if isinstance(h_dewarp, str):
        hvals = [float(x.strip()) for x in h_dewarp.split(",") if x.strip()!=""]
        if len(hvals) == 9:
            H_d = np.array(hvals, dtype=np.float64).reshape(3,3)

    # Center for vignetting (designed optical center)
    # Note: guide says CenterX, CenterY from Calibrated Optical Center X/Y
    cx_design = float(g("CalibratedOpticalCenterX", "Calibrated Optical Center X", default=0.0))
    cy_design = float(g("CalibratedOpticalCenterY", "Calibrated Optical Center Y", default=0.0))

    # Photometric fields
    bits = int(g("BitsPerSample", "Bits Per Sample", default=16))
    black = float(g("BlackLevel", "Black Level", default=0))
    gain  = float(g("SensorGain", "Sensor Gain", default=1.0))
    exp_raw = g("ExposureTime", "Exposure Time", default=None)
    exp_us = None
    if exp_raw is None:
        exp_us = 1000.0  # fallback: 1000 us
    else:
        # Si es una fracción "1/1250"
        if isinstance(exp_raw, str) and "/" in exp_raw:
            try:
                a, b = exp_raw.split("/")
                seconds = float(a) / float(b)
                exp_us = seconds * 1e6
            except Exception:
                try:
                    exp_us = float(exp_raw) * 1e6
                except Exception:
                    exp_us = 1000.0
        else:
            # numérico o string que representa float
            try:
                val = float(exp_raw)
                # heurística: si val < 10 it's almost certainly seconds (e.g. 0.0008),
                # if val > 1000 probably already in microseconds, so leave
                if val < 10.0:
                    # treat as seconds -> convert to microseconds
                    exp_us = val * 1e6
                else:
                    # treat as microseconds already
                    exp_us = val
            except Exception:
                exp_us = 1000.0
    pCam = float(g("SensorGainAdjustment", "Sensor Gain Adjustment", default=1.0))
    irradiance = float(g("Irradiance"))
    band = str(g("BandName", "Band Name", default="")).upper()

    return dict(
        bits=bits, black=black, gain=gain, exp_us=exp_us, pCam=pCam,
        irradiance=irradiance, band=band,
        kpoly=kpoly, cx_design=cx_design, cy_design=cy_design,
        fx=fx, fy=fy, cx=cx, cy=cy, k1=k1, k2=k2, p1=p1, p2=p2, k3=k3,
        H=H, H_dewarp=H_d
    )

def load_gray16(path):
    I = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if I is None:
        raise RuntimeError(f"Could not read {path}")
    if I.ndim == 3:
        I = cv2.cvtColor(I, cv2.COLOR_BGR2GRAY)
    return I


def vignetting_correct(I, meta):
    """
    I_out = I * (k[5]*r^6 + k[4]*r^5 + ... + k[0]*r + 1.0)
    r = sqrt((x-CenterX)^2 + (y-CenterY)^2), Center from calibrated optical center.
    """
    k = meta["kpoly"]
    if k is None:
        return I
    h, w = I.shape[:2]
    # meshgrid in pixel coords (x to right, y down)
    xs = np.arange(w, dtype=np.float64)
    ys = np.arange(h, dtype=np.float64)
    X, Y = np.meshgrid(xs, ys)
    cx = meta["cx_design"]
    cy = meta["cy_design"]
    r = np.sqrt((X - cx)**2 + (Y - cy)**2)
    # Polynomial: k0..k5 with powers r^1..r^6 (per guide)
    r1 = r
    r2 = r1*r
    r3 = r2*r
    r4 = r3*r
    r5 = r4*r
    r6 = r5*r
    poly = 1.0 + k[0]*r1 + k[1]*r2 + k[2]*r3 + k[3]*r4 + k[4]*r5 + k[5]*r6
    return (I.astype(np.float64) * poly).astype(I.dtype)

def undistort_with_meta(I, meta):
    """
    OpenCV undistort using Dewarp Data.
    Camera matrix uses (fx, 0, CenterX+cx), (0, fy, CenterY+cy), (0,0,1) as per guide.
    """
    fx, fy, cx, cy = meta["fx"], meta["fy"], meta["cx"], meta["cy"]
    k1, k2, p1, p2, k3 = meta["k1"], meta["k2"], meta["p1"], meta["p2"], meta["k3"]
    if None in (fx, fy, cx, cy, k1, k2, p1, p2, k3):
        return I
    h, w = I.shape[:2]
    cx_vign = meta["cx_design"]
    cy_vign = meta["cy_design"]
    K = np.array([[fx, 0, cx_vign + cx],
                  [0,  fy, cy_vign + cy],
                  [0,   0,          1]], dtype=np.float64)
    D = np.array([k1, k2, p1, p2, k3], dtype=np.float64)
    # Per guide, avoid changing newcameramtx; use original K
    return cv2.undistort(I, K, D, None, K)

def apply_hmatrix(I, H, out_shape=None):
    if H is None:
        return I
    h, w = I.shape[:2]
    if out_shape is None:
        out_shape = (w, h)
    return cv2.warpPerspective(I, H, out_shape, flags=cv2.INTER_LINEAR)

def img_signal(I, bits, black, gain, exp_us):
    # Normalize raw to [0,1], subtract normalized black, divide by gain * (exp/1e6)
    denom = float(2**bits)
    I_norm = I.astype(np.float64) / denom
    black_norm = float(black) / denom
    cam = (I_norm - black_norm)
    cam[cam < 0] = 0.0
    return cam / (gain * (exp_us / 1e6))


def per_band_pipeline(path):
    """
    Load -> vignetting -> undistort -> HMatrix warp -> return corrected image and metadata.
    """
    I0 = load_gray16(path)
    m = exif_read(path)

    I1 = vignetting_correct(I0, m)
    I2 = undistort_with_meta(I1, m)
    I3 = apply_hmatrix(I2, m["H"], out_shape=(I2.shape[1], I2.shape[0]))
    return I3, m

def compute_reflectance(Icorr, meta):
    cam = img_signal(Icorr, meta["bits"], meta["black"], meta["gain"], meta["exp_us"])   # Eq. 9
    #print(f"Meta values: pCam={meta['pCam']}, irradiance={meta['irradiance']}, gain={meta['gain']}, exp_us={meta['exp_us']}")
    # reflectance_X = (X_camera * pCam_X) / (Irradiance_X)
    irradiance = meta["irradiance"]
    ref = (cam * meta["pCam"]) / max(irradiance, 1e-12)
    return ref

def ndvi_to_drgb(rgb_path, red_path):
    """
    NDVI currently on 'designed image plane'.
    Apply Dewarp HMatrix (designed → designed RGB image plane).
    """
    rgb = cv2.imread(rgb_path, cv2.IMREAD_UNCHANGED)
    if rgb is None:
        raise RuntimeError("Cannot read RGB image")
    m = exif_read(red_path)
    H_dewarp = m["H_dewarp"]
    h_out, w_out =  rgb.shape[:2]
    
    return H_dewarp, h_out, w_out

def read_mask(mask_path):
    mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise RuntimeError(f"Could not read mask image: {mask_path}")
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    # finding contours of the mask
    cnt, _= cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # drawing square around the largest contour
    if len(cnt) == 0:
        return None
    largest_contour = max(cnt, key=cv2.contourArea)
    x,y,w,h = cv2.boundingRect(largest_contour)
    return (x, y, w, h)

def build_resnet18_6ch(num_classes=2):
    model = resnet18(weights=None)

    # Modify first conv layer: 6 input channels → 64 output channels
    model.conv1 = nn.Conv2d(
        9, 64,
        kernel_size=7,
        stride=2,
        padding=3,
        bias=False
    )

    # Final classifier
    model.fc = nn.Linear(512, num_classes)

    return model


def predict_hypercube_using_worker_model(cube, tile_size=256, num_tiles=16, device="cpu"):
    """Use the per-worker global WORKER_MODEL rather than loading a model every call."""
    global WORKER_MODEL
    if WORKER_MODEL is None:
        raise RuntimeError("Worker model not initialized. Use Pool(initializer=init_worker).")
    model = WORKER_MODEL
    arr = cube.transpose(1,2,0)

    predictions = []
    # If your data is small, consider reducing num_tiles
    for _ in range(num_tiles):
        h, w, _ = arr.shape
        if h <= tile_size or w <= tile_size:
            top = 0
            left = 0
            tile = arr[top:top+tile_size, left:left+tile_size, :]
        else:
            top = random.randint(0, h - tile_size)
            left = random.randint(0, w - tile_size)
            tile = arr[top:top+tile_size, left:left+tile_size, :]

        tile_t = torch.from_numpy(tile).permute(2,0,1).float().unsqueeze(0).to(device)
        with torch.no_grad():
            out = model(tile_t)
            pred = torch.argmax(out, dim=1).item()
            predictions.append(pred)

    final = max(set(predictions), key=predictions.count)
    return final

def process_set(args):
    """
    PROCESA UN LOTE: green, red, red edge, nir → reflectancias + índices
    Y GUARDA hypercube.npz
    """

    rgb_path= args
    base = os.path.basename(rgb_path)
    nir_path   = rgb_path.replace("_D.JPG", "_MS_NIR.TIF")
    green_path = rgb_path.replace("_D.JPG", "_MS_G.TIF")
    redge_path = rgb_path.replace("_D.JPG", "_MS_RE.TIF")
    red_path   = rgb_path.replace("_D.JPG", "_MS_R.TIF")

    if not all(os.path.exists(p) for p in [nir_path, green_path, redge_path]):
        print(f"Saltando {base}: faltan bandas.")
        return

    mask_path  = rgb_path.replace("_D.JPG", "_D__mask.TIF") 
    if not os.path.exists(mask_path):
        print(f"Saltando {base}: no hay máscara.")
        return (base, None)
    try:
        mask_box = read_mask(mask_path)
        x, y, w, h = mask_box # EZQUINA SUPERIOR IZQUIERDA, ANCHO, ALTO

        # ---- Calibración de cada banda ----
        nir_corr, mn   = per_band_pipeline(nir_path)
        red_corr, mr   = per_band_pipeline(red_path)
        green_corr, mg = per_band_pipeline(green_path)
        redge_corr, mre = per_band_pipeline(redge_path)

        # ---- Reflectancias ----
        nir_ref   = compute_reflectance(nir_corr, mn).astype(np.float32)
        red_ref   = compute_reflectance(red_corr, mr).astype(np.float32)
        green_ref = compute_reflectance(green_corr, mg).astype(np.float32)
        redge_ref = compute_reflectance(redge_corr, mre).astype(np.float32)
        
        # ---- Índices ----
        eps = 1e-12

        ndvi  = (nir_ref - red_ref) / (nir_ref + red_ref + eps)
        gndvi = (nir_ref - green_ref) / (nir_ref + green_ref + eps)
        ndre  = (nir_ref - redge_ref) / (nir_ref + redge_ref + eps)
        ccci  = (ndvi - gndvi) / (ndvi + gndvi + eps)

        sr = nir_ref / (red_ref + eps)
        msr = (sr - 1.0) / (np.sqrt(sr) + 1.0 + eps)

        L = 0.5
        savi = ((1 + L) * (nir_ref - red_ref)) / (nir_ref + red_ref + L + eps)

        # ---- Warp al plano RGB ----
        H_dewarp, h_out, w_out = ndvi_to_drgb(rgb_path, red_path)
        indices = [ndvi, gndvi, ndre, ccci, savi]
        aligned_idx = []

        for idx in indices:
            idx = idx.clip(-1.0, 1.0)
            aligned = cv2.warpPerspective(idx, H_dewarp, (w_out, h_out), flags=cv2.INTER_LINEAR)
            aligned = aligned[y:y + h, x:x + w].astype(np.float32)
            aligned_idx.append(aligned)

        # ---- Warp de reflectancias ----
        aligned_refs = []
        for ref in [green_ref, red_ref, redge_ref, nir_ref]:
            A = cv2.warpPerspective(ref, H_dewarp, (w_out, h_out), flags=cv2.INTER_LINEAR)
            A = A[y:y + h, x:x + w].astype(np.float32)
            aligned_refs.append(A)

        # ---- CREAR HYPERCUBO ----
        # Orden: Green, Red, RedEdge, NIR, NDVI, GNDVI, NDRE, CCCI, MSR, SAVI
        hypercube = np.stack(
            aligned_refs + aligned_idx,
            axis=0
        ).astype(np.float32)

        prediction = predict_hypercube_using_worker_model(
            cube = hypercube,
            tile_size=256,
            num_tiles=16,
            device="cpu"
        )
        #print("prediccion",base, prediction)
        return (base, prediction)

    except Exception as e:
        print(f"Error procesando {base}: {e}")
        return (base, None)


def generate_predictions(images_path, model_path="best_resnet18_6ch.pth", max_workers=None):
    rgb_files = sorted(glob.glob(os.path.join(images_path, "*_D.JPG"))) # Aqui se puede insertar la lista de imágenes R
    if len(rgb_files) == 0:
        print("No se encontraron imágenes R.")
        return

    # Choose conservative worker count
    if max_workers is None:
        # leave one CPU free for OS tasks
        max_workers = max(1, cpu_count() - 1)

    #print(f"Procesando {len(rgb_files)} sets usando {max_workers} procesos...\n")

    args_list = rgb_files
    #init_worker(model_path)
    # Each worker will call init_worker(model_path) once at start
    with Pool(processes=max_workers-10, initializer=init_worker, initargs=(model_path,)) as p:
        results = p.map(process_set, args_list)
    # results = []
    # for path in args_list:
    #     result = process_set(path)
    #     results.append(result)

    print("\nResultados de las predicciones:")
    for res in results:
        if res is not None:
            base, pred = res
            if pred is not None:
                print(f"{base}: Clase {pred}")
            else:
                print(f"{base}: No se pudo predecir.")
    print("\nProcesamiento COMPLETADO.\n")


# =======================================================
#                  MAIN
# =======================================================
if __name__ == "__main__":
        images_path = fr"C:\Users\jhonz\OneDrive - CESAL\Fase_2\data\toma_1\drone_imgs"
        generate_predictions(
            images_path=images_path,
        )
