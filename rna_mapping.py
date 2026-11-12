"""CUCM RNA seconds to Webex ring cycles: advisory only until measured.

No Webex API fields are generated from an unverified conversion.
"""
import json
import math
from pathlib import Path


def load_calibration(path):
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    seconds = data.get('measuredSecondsPerRing')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not (1 <= seconds <= 15):
        raise ValueError('measuredSecondsPerRing must be a measured number between 1 and 15')
    if data.get('validatedByTestCalls') is not True:
        raise ValueError('Calibration requires validatedByTestCalls=true')
    if not str(data.get('measurementNotes') or '').strip():
        raise ValueError('Calibration requires measurementNotes')
    return data


def assess(seconds, calibration=None):
    if seconds in (None, ''):
        return {'status':'NOT_CONFIGURED','cucmSeconds':None,'webexRings':None,
                'estimatedWebexSeconds':None,'estimatedDeviationSeconds':None}
    try:
        value = float(seconds)
    except (ValueError, TypeError):
        return {'status':'INVALID_CUCM_TIMEOUT','cucmSeconds':seconds,'webexRings':None,
                'estimatedWebexSeconds':None,'estimatedDeviationSeconds':None}
    if not math.isfinite(value) or value <= 0:
        return {'status':'INVALID_CUCM_TIMEOUT','cucmSeconds':seconds,'webexRings':None,
                'estimatedWebexSeconds':None,'estimatedDeviationSeconds':None}
    base = {'cucmSeconds':value,'webexRings':None,'estimatedWebexSeconds':None,
            'estimatedDeviationSeconds':None}
    if not calibration:
        return {'status':'MEASUREMENT_REQUIRED',**base,
                'note':'No assumed seconds-per-ring. Measure Webex call behavior before mapping.'}
    rate = calibration['measuredSecondsPerRing']
    # Use nearest integer; ties select fewer rings to avoid delayed failover.
    rings = max(1, math.floor(value/rate + 0.5))
    estimated = round(rings*rate, 3)
    return {'status':'CALIBRATED_ADVISORY',**base,'webexRings':rings,
            'estimatedWebexSeconds':estimated,
            'estimatedDeviationSeconds':round(estimated-value,3),
            'measurementNotes':calibration['measurementNotes'],
            'note':'Advisory only: Webex hunt-group API support and live readback still require validation.'}
