import os
import numpy as np
import cv2
import joblib
from skimage.feature import graycomatrix, graycoprops
import pandas as pd

from core.constants import THRESH_STAGES_DEFAULT, UNCERTANTY_VALUE
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


#THRESH_STAGES_DEFAULT = {"Pre-floracion": 2.8,"Floracion": 2.6, "Cuajado": 2.0, "Fruto": 1.8, "Cosecha": 2.4}

def get_class_def_nitrogen(thresh_stages, nitrogen_value, stage, uncertanty):
    if thresh_stages[stage] + uncertanty <= nitrogen_value:
        return "saludable"
    elif thresh_stages[stage] - uncertanty < nitrogen_value:
        return "posible-deficiencia"
    else:
        return "deficiencia"
                
class NitrogenDefClassiferML:
    def __init__(self, thresh_stages = THRESH_STAGES_DEFAULT, uncertanty = UNCERTANTY_VALUE):
        self.uncertanty = uncertanty
        
        model_path = resource_path(os.path.join("assets", "models", "hgb_model.pkl"))
        self.model = joblib.load(model_path)
        
        features_path = resource_path(os.path.join("assets", "models", "hgb_features.pkl"))
        self.feature_columns = joblib.load(features_path)
        self.thresh_stages = thresh_stages
    
    def _extract_features_from_cube(sef, cube):
        features = {}
        names = ["green","red","rededge","nir","ndvi","gndvi","ndre","ccci","savi"]

        selected = ["green","red","rededge","nir","ndvi","ndre","ccci"]

        for n in selected:
            b = cube[names.index(n)]
            features[f"{n}_mean"] = np.mean(b)
            features[f"{n}_std"] = np.std(b)

        ndre = cube[names.index("ndre")]
        ccci = cube[names.index("ccci")]

        features["ndre_p90"] = np.percentile(ndre, 90)
        features["ccci_p90"] = np.percentile(ccci, 90)

        ndvi = cube[names.index("ndvi")]
        ndvi_scaled = ((ndvi - ndvi.min()) / (np.ptp(ndvi)+1e-6) * 255).astype(np.uint8)

        glcm = graycomatrix(ndvi_scaled, [1], [0], 256, True, True)

        features["ndvi_contrast"] = graycoprops(glcm, "contrast")[0,0]
        features["ndvi_homogeneity"] = graycoprops(glcm, "homogeneity")[0,0]

        features["ndre_high_fraction"] = np.mean(ndre > 0.3)
        features["ccci_high_fraction"] = np.mean(ccci > 0.5)

        return features

    def _get_class_def_nitrogen(self, nitrogen_value, stage):
        if self.thresh_stages[stage] + self.uncertanty <= nitrogen_value:
            return "saludable"
        elif self.thresh_stages[stage] - self.uncertanty < nitrogen_value:
            return "posible-deficiencia"
        else:
            return "deficiencia"
    
    def predict(self, cube, stage):
        feats = self._extract_features_from_cube(cube[:,:, :-1])
        df = pd.DataFrame([feats])

        df = df.reindex(columns=self.feature_columns, fill_value=0)

        pred = self.model.predict(df.values)[0]

        return pred, get_class_def_nitrogen(self.thresh_stages, pred, stage, self.uncertanty)
    

if __name__ == "__main__":
    print()