
import argparse, json, subprocess, numpy as np, cv2, shlex, math, os, glob


def modern_ldp_ndvi_colormap(ndvi):
    """
    Robust, vectorized NDVI -> RGB colormap with smooth linear interpolation
    across defined color segments. Expects ndvi in [-1, 1].
    Returns uint8 RGB image (H, W, 3).
    """
    ndvi = np.asarray(ndvi, dtype=np.float32)
    h, w = ndvi.shape
    colored = np.zeros((h, w, 3), dtype=np.uint8)

    # Define segments (low, high, color_low(RGB), color_high(RGB))
    segments = [
        (-1.0, -0.6, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 251], dtype=np.float32)),   # black -> blue
        (-0.6, 0.0, np.array([0, 0, 251], dtype=np.float32), np.array([220, 0, 251], dtype=np.float32)), # blue -> purple
        (0.0, 0.5, np.array([220, 0, 251], dtype=np.float32), np.array([220, 0, 120], dtype=np.float32)), # purple -> pink
        (0.5, 0.8, np.array([220, 0, 120], dtype=np.float32),  np.array([220, 100, 0], dtype=np.float32)),  # pink -> dark orange
        (0.8, 0.9, np.array([220, 100, 0], dtype=np.float32),  np.array([220, 240, 0], dtype=np.float32)),  # dark orange -> yellow
        (0.9, 1.0, np.array([220, 240, 0], dtype=np.float32),  np.array([20, 80, 0], dtype=np.float32)),    # yellow -> green
    ]

    # Assign for each segment
    for low, high, c_low, c_high in segments:
        if high == low:
            continue
        mask = (ndvi >= low) & (ndvi < high)
        if not np.any(mask):
            continue
        t = (ndvi[mask] - low) / (high - low)
        # Interpolate per-channel
        cols = (c_low[None, :] * (1.0 - t[:, None]) + c_high[None, :] * (t[:, None])).astype(np.uint8)
        colored[mask] = cols

    # handle exact 1.0 (inclusive)
    mask_one = (ndvi >= 1.0)
    if np.any(mask_one):
        colored[mask_one] = segments[-1][3].astype(np.uint8)  # final color_high

    return colored

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
    exp_us = float(g("ExposureTime", "Exposure Time", default=1000))
    pCam = float(g("SensorGainAdjustment", "Sensor Gain Adjustment", default=1.0))
    irradiance = float(g("Irradiance", default=1.0))
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

def ecc_align(src, dst):
    """
    Optional: exposure-difference alignment (Method 1 in guide): ECC Maximization.
    Returns warped src aligned to dst (affine).
    """
    # downscale for robustness/speed
    h, w = dst.shape[:2]
    scale = 0.5 if max(h, w) > 1200 else 1.0
    if scale != 1.0:
        src_s = cv2.resize(src, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
        dst_s = cv2.resize(dst, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
    else:
        src_s, dst_s = src.copy(), dst.copy()

    # blur as recommended
    src_s = cv2.GaussianBlur(src_s, (5,5), 0)
    dst_s = cv2.GaussianBlur(dst_s, (5,5), 0)

    # ECC with affine model
    warp_mode = cv2.MOTION_AFFINE
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-6)
    try:
        cc, warp = cv2.findTransformECC(dst_s, src_s, warp, warp_mode, criteria, None, 5)
    except cv2.error:
        return src  # fallback: no change

    if scale != 1.0:
        # upscale affine to full res
        warp_full = warp.copy()
        warp_full[:,2] /= scale
        return cv2.warpAffine(src, warp_full, (w, h), flags=cv2.INTER_LINEAR)
    else:
        return cv2.warpAffine(src, warp, (w, h), flags=cv2.INTER_LINEAR)

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
    # reflectance_X = (X_camera * pCam_X) / (Irradiance_X)
    ref = (cam * meta["pCam"]) / max(meta["irradiance"], 1e-12)
    return ref

def ndvi_to_drgb(ndvi_dip,rgb_path, red_path):
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
    ndvi_on_drgb = cv2.warpPerspective(ndvi_dip, H_dewarp, (w_out, h_out), flags=cv2.INTER_LINEAR)
    return ndvi_on_drgb

def generate_ndvi_images(images_path, output_dir="./ndvi_aligned/", show_palette=False, use_edges=False, use_window=True):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_ecc", action="store_true", help="extra ECC alignment after HMatrix")
    args = ap.parse_args()
    os.makedirs(output_dir, exist_ok=True)

    # Find Red band files and form NIR pair names
    red_files = sorted(glob.glob(os.path.join(images_path, "*_MS_R.TIF")))

    if len(red_files) == 0:
        print("No existen archivos con el formato '*_MS_R.TIF' found in", images_path)
        return

    processed = 0
    for red_path in red_files:
        base = os.path.basename(red_path)
        nir_path = red_path.replace("_MS_R.TIF", "_MS_NIR.TIF")
        rgb_path = red_path.replace("_MS_R.TIF", ".JPG")

        if not os.path.exists(nir_path):
            print(f"Saltando a siguiente {base}: no existe imagen NIR ({nir_path})")
            continue

        # Load grayscale bands
        nir_corr, mn = per_band_pipeline(nir_path)
        red_corr, mr = per_band_pipeline(red_path)

        if red_corr is None or nir_corr is None:
            print(f"Error al cargar imagenes: {red_path} o {nir_path}")
            continue

        if red_corr.shape != nir_corr.shape:
            print(f"Las imagenes tienen dimensione distintas {base}: rojo {red_corr.shape}, nir {nir_corr.shape}. Saltando al siguiente.")
            continue

        if args.run_ecc:
            red_corr = ecc_align(red_corr.astype(np.float32), nir_corr.astype(np.float32))

        # Convert each band to reflectance (Eq. 4–6 use Irradiance already as LS*pLS)
        nir_ref = compute_reflectance(nir_corr, mn)
        red_ref = compute_reflectance(red_corr, mr)

        # NDVI (Eq. 6)
        eps = 1e-12
        ndvi = (nir_ref - red_ref) / (nir_ref + red_ref + eps)
        ndvi = np.clip(ndvi, -1.0, 1.0).astype(np.float32)
        colored_ndvi = modern_ldp_ndvi_colormap(ndvi)

        # Aligned to RGB designed plane
        aligned_ndvi = ndvi_to_drgb(colored_ndvi, rgb_path, red_path)

        save_bgr = cv2.cvtColor(aligned_ndvi, cv2.COLOR_RGB2BGR) # Change this to save only ndvi or alined ndvi
        out_base = os.path.splitext(base)[0]
        out_png = os.path.join(output_dir, f"{out_base}_aligned_NDVI.png")
        #out_ndvi_npy = os.path.join(output_dir, f"{out_base}_NDVI.npy")

        # Save outputs
        ok = cv2.imwrite(out_png, save_bgr)
        if not ok:
            print(f"Failed to write {out_png}")
        else:
            print(f"Saved {out_png}")

        # also save raw NDVI float array for later analysis
        # np.save(out_ndvi_npy, ndvi.astype(np.float32))
        # print(f"Saved NDVI array {out_ndvi_npy}")

        processed += 1

        print(f"Procesamiento completado. {processed}/{len(red_files)} pares procesados.")



if __name__ == "__main__":
    images_path = r"C:/Users/jhonz/Desktop/CESAL/NutrientDetection/data/toma_0/drone_campo"
    output_dir = r"C:/Users/jhonz\Desktop/CESAL/NutrientDetection/data/toma_0/ndvi_aligned"
    generate_ndvi_images(images_path, output_dir=output_dir, show_palette=False, use_edges=False, use_window=True)