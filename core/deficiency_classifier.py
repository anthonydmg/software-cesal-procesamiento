import torch
import torch.nn as nn
import random
from torchvision.models import resnet18
import os
import numpy as np
import cv2

from core.utils import resource_path

def load_gray16(path):
    I = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    print("I:", I.shape)
    print("I.ndim:", I.ndim)
    if I is None:
        raise RuntimeError(f"Could not read {path}")
    if I.ndim == 3 and I.shape[-1] > 1:
        I = cv2.cvtColor(I, cv2.COLOR_BGR2GRAY)
    if I.shape[-1] == 1:
        I = I.squeeze()
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


def img_signal(I, bits, black, gain, exp_raw):
    # Normalize raw to [0,1], subtract normalized black, divide by gain * (exp/1e6)
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

    denom = float(2**bits)
    I_norm = I.astype(np.float64) / denom
    black_norm = float(black) / denom
    cam = (I_norm - black_norm)
    cam[cam < 0] = 0.0
    return cam / (gain * (exp_us / 1e6))


def per_band_pipeline(path, metadata):
    """
    Load -> vignetting -> undistort -> HMatrix warp -> return corrected image and metadata.
    """
    I0 = load_gray16(path)

    I1 = vignetting_correct(I0, metadata)
    I2 = undistort_with_meta(I1, metadata)
    H_cal = np.array(metadata["H_cal"])
    I3 = apply_hmatrix(I2, H_cal, out_shape=(I2.shape[1], I2.shape[0]))
    return I3, metadata

def compute_reflectance(Icorr, meta):
    cam = img_signal(Icorr, meta["bits"], meta["black"], meta["gain"], meta["exp_us"])   # Eq. 9
    #print(f"Meta values: pCam={meta['pCam']}, irradiance={meta['irradiance']}, gain={meta['gain']}, exp_us={meta['exp_us']}")
    # reflectance_X = (X_camera * pCam_X) / (Irradiance_X)
    irradiance = meta["irradiance"]
    ref = (cam * meta["pCam"]) / max(irradiance, 1e-12)

    #cam = img_signal(Icorr, meta["bits"], meta["black"], meta["gain"], meta["exp_us"])   # Eq. 9
    # reflectance_X = (X_camera * pCam_X) / (Irradiance_X)
    #ref = (cam * meta["pCam"]) / max(meta["irradiance"], 1e-12)
    return ref

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


class NitrogenDefClassifer:
    _model = None
    #_model_path = None
    _device = "cpu"

    # -------------------------------------------------------------
    # CONFIGURACIÓN INICIAL
    # -------------------------------------------------------------
    @classmethod
    def configure(cls, model_path, device="cpu"):
        cls._model_path = model_path
        cls._device = device

    # -------------------------------------------------------------
    # ESTABLECER DEVICE ANTES O DESPUÉS DEL LOAD
    # -------------------------------------------------------------
    @classmethod
    def set_device(cls, device):
        cls._device = device
        if cls._model is not None:
            cls._model.to(device)

    # -------------------------------------------------------------
    # LAZY-LOAD DEL MODELO
    # -------------------------------------------------------------
    @classmethod
    def get(cls):
        """Retorna el modelo. Lo carga solo si aún no está cargado."""
        if cls._model is None:

            #if cls._model_path is None:
            #    raise RuntimeError("Primero debes llamar ModelManager.configure().")

            # Construir arquitectura
            model = build_resnet18_6ch()
            
            # Cargar pesos al CPU
            state = torch.load(resource_path(os.path.join("assets", "models", "best_resnet18_6ch.pth")), map_location="cpu")
            model.load_state_dict(state)

            # Mover a device deseado
            model.to(cls._device)
            model.eval()

            cls._model = model

        return cls._model

    # -------------------------------------------------------------
    # LIMPIAR EL MODELO DE LA MEMORIA
    # -------------------------------------------------------------
    @classmethod
    def unload(cls):
        if cls._model is not None:
            del cls._model
            cls._model = None

            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

    @classmethod
    @torch.no_grad()
    def predict(cls, cube, tile_size=256, num_tiles=16):
        """Realiza predicción usando lazy-loading del modelo."""
        model = cls.get()  # asegura que el modelo esté cargado
        #input_tensor = input_tensor.to(cls._device)
        arr = cube.transpose(1,2,0)

        predictions = []
        tiles = []
        # If your data is small, consider reducing num_tiles
        for _ in range(num_tiles):
            h, w, _ = arr.shape
            if h <= tile_size or w <= tile_size:
                top = 0
                left = 0
            else:
                top = random.randint(0, h - tile_size)
                left = random.randint(0, w - tile_size)

            tile = arr[top:top+tile_size, left:left+tile_size, :]
            tiles.append(tile)
        batch = np.stack(tiles, axis=0)
        batch_t = torch.from_numpy(batch).permute(2,0,1).float().unsqueeze(0).to(cls._device)

        with torch.no_grad():
            out = model(batch_t)
            preds = torch.argmax(out, dim=1).cpu().numpy()

        final = np.bincount(preds).argmax()
        return final

    @classmethod
    def build_cube_and_predict(cls, rgb_path, mask_tree, corner, all_metadata_images):
        base = os.path.basename(rgb_path)
        nir_path   = rgb_path.replace("_D.JPG", "_MS_NIR.TIF")
        green_path = rgb_path.replace("_D.JPG", "_MS_G.TIF")
        redge_path = rgb_path.replace("_D.JPG", "_MS_RE.TIF")
        red_path   = rgb_path.replace("_D.JPG", "_MS_R.TIF")

        nir_basename = os.path.basename(nir_path)
        green_basename = os.path.basename(green_path)
        redge_basename = os.path.basename(redge_path)
        red_basename = os.path.basename(red_path)


        if not all(os.path.exists(p) for p in [nir_path, green_path, redge_path]):
            print(f"Saltando {base}: faltan bandas.")
            return
        
       
        #rgb_file_metadata = all_metadata_images.get(base, None)
        nir_file_metadata = all_metadata_images.get(nir_basename, None)
        green_file_metadata = all_metadata_images.get(green_basename, None)
        redge_file_metadata = all_metadata_images.get(redge_basename, None)
        red_file_metadata = all_metadata_images.get(red_basename, None)
        

         # ---- Calibración de cada banda ----
        nir_corr, mn   = per_band_pipeline(nir_path, nir_file_metadata)
        red_corr, mr   = per_band_pipeline(red_path, red_file_metadata)
        green_corr, mg = per_band_pipeline(green_path, green_file_metadata)
        redge_corr, mre = per_band_pipeline(redge_path, redge_file_metadata)

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

        mcari = ((redge_ref - red_ref) - 0.2 * (red_ref - green_ref)) * (redge_ref / (red_ref + eps))

        rgb = cv2.imread(rgb_path, cv2.IMREAD_UNCHANGED)
        h_out, w_out =  rgb.shape[:2]
        H_dewarp = red_file_metadata["H_dewarp"]
        H_dewarp = np.array(H_dewarp)
        x, y = corner
        h, w = mask_tree.shape[:2]
        # ---- Warp al plano RGB ----
        
        #H_dewarp, h_out, w_out = ndvi_to_drgb(rgb_path, red_path)
        print("ndvi mean", ndvi.mean())
        indices = [ndvi, gndvi, ndre, ccci, savi,mcari] 
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

        prediction = cls.predict(hypercube[:-1,:,:])

        return prediction, hypercube
        

if __name__ == "__main__":
    print()