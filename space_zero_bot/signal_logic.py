# space_zero_bot/signal_logic.py
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from scipy.stats import linregress # Import linregress
import pandas_ta as ta

def detect_peaks_troughs(df: pd.DataFrame, high_col='high', low_col='low', order=5, prominence_threshold_factor=0.005):
    # Detects peaks (swing highs) and troughs (swing lows) in price data.
    # Prominence is a measure of how much a peak stands out.
    # Threshold factor is relative to mean price for that series.
    if df.empty or not {high_col, low_col}.issubset(df.columns):
        return [], []

    # Ensure data is float for calculations
    try:
        df_high = df[high_col].astype(float)
        df_low = df[low_col].astype(float)
    except ValueError:
        # print("Could not convert high/low columns to float for peak detection.")
        return [], []

    if df_high.isna().all() or df_low.isna().all():
        return [], []

    # Calculate prominence dynamically.
    # Using mean of the 'high' series as a reference for prominence calculation.
    mean_price_for_prominence = df_high.mean()

    if pd.isna(mean_price_for_prominence) or mean_price_for_prominence == 0:
         # Fallback if mean_price is unusable (e.g. all NaNs, or all zeros)
         prominence_val = 0.001
    else:
        prominence_val = abs(mean_price_for_prominence * prominence_threshold_factor)

    # Ensure prominence_val is a positive scalar
    if not (np.isscalar(prominence_val) and np.isfinite(prominence_val) and prominence_val > 0):
        prominence_val = 0.001 # Default small prominence if calculation failed

    peak_indices, _ = find_peaks(df_high.values, distance=order, prominence=prominence_val)
    # For troughs, invert the series (make lows positive peaks) and find peaks
    trough_indices, _ = find_peaks(-df_low.values, distance=order, prominence=prominence_val)

    return peak_indices.tolist(), trough_indices.tolist()

def determine_trend_from_emas(df: pd.DataFrame, ema_short_col='EMA_50', ema_long_col='EMA_200'):
    if df.empty or not {ema_short_col, ema_long_col}.issubset(df.columns):
        return "Indecisive (EMA columns missing)"

    # Drop NaNs from EMA columns for reliable last value access
    ema_short_series = df[ema_short_col].dropna()
    ema_long_series = df[ema_long_col].dropna()

    if ema_short_series.empty or ema_long_series.empty:
        return "Indecisive (EMAs have no non-NaN values)"

    latest_ema_short = ema_short_series.iloc[-1]
    latest_ema_long = ema_long_series.iloc[-1]

    if latest_ema_short > latest_ema_long:
        return "Uptrend (EMA)"
    elif latest_ema_short < latest_ema_long:
        return "Downtrend (EMA)"
    else:
        return "Indecisive (EMAs equal)"

def confirm_trend_with_market_structure(df: pd.DataFrame, current_ema_trend: str,
                                        peak_indices: list, trough_indices: list,
                                        high_col='high', low_col='low', lookback_swings=2):
    if not peak_indices or not trough_indices:
        return "Trend Not Confirmed (Not enough swing points)"

    # Ensure indices are within DataFrame bounds
    valid_peak_indices = [idx for idx in peak_indices if 0 <= idx < len(df)]
    valid_trough_indices = [idx for idx in trough_indices if 0 <= idx < len(df)]

    if not valid_peak_indices or not valid_trough_indices:
        return "Trend Not Confirmed (Swing point indices out of bounds)"

    swing_highs_series = df.iloc[valid_peak_indices][high_col]
    swing_lows_series = df.iloc[valid_trough_indices][low_col]

    if len(swing_highs_series) < lookback_swings or len(swing_lows_series) < lookback_swings:
        return f"Trend Not Confirmed (Need at least {lookback_swings} valid swing highs and lows)"

    recent_highs = swing_highs_series.tail(lookback_swings).values
    recent_lows = swing_lows_series.tail(lookback_swings).values

    # Check for strictly increasing/decreasing sequences
    is_hh = all(recent_highs[i] < recent_highs[i+1] for i in range(len(recent_highs)-1))
    is_hl = all(recent_lows[i] < recent_lows[i+1] for i in range(len(recent_lows)-1))
    is_lh = all(recent_highs[i] > recent_highs[i+1] for i in range(len(recent_highs)-1))
    is_ll = all(recent_lows[i] > recent_lows[i+1] for i in range(len(recent_lows)-1))

    if current_ema_trend == "Uptrend (EMA)":
        if is_hh and is_hl: return "Confirmed Uptrend"
        if is_hh: return "Partial Uptrend (Higher Highs only)"
        if is_hl: return "Partial Uptrend (Higher Lows only)"
        return "Uptrend (EMA) Not Confirmed by Recent Structure"
    elif current_ema_trend == "Downtrend (EMA)":
        if is_lh and is_ll: return "Confirmed Downtrend"
        if is_lh: return "Partial Downtrend (Lower Highs only)"
        if is_ll: return "Partial Downtrend (Lower Lows only)"
        return "Downtrend (EMA) Not Confirmed by Recent Structure"

    return "Trend Not Confirmed (EMA Indecisive or Mismatch)"


def identify_sr_levels(df: pd.DataFrame, peak_indices: list, trough_indices: list,
                       high_col='high', low_col='low', num_levels_to_return=5):
    if df.empty:
        return {"supports": [], "resistances": []}

    valid_peak_indices = [idx for idx in peak_indices if 0 <= idx < len(df)]
    valid_trough_indices = [idx for idx in trough_indices if 0 <= idx < len(df)]

    recent_resistances = []
    if valid_peak_indices:
        # Get unique values from recent peaks (more than num_levels_to_return initially to get variety)
        # then take the top N highest ones from this recent set
        raw_recent_peak_values = df.iloc[valid_peak_indices][high_col].astype(float).tail(num_levels_to_return * 3).tolist()
        unique_recent_resistances = sorted(list(set(raw_recent_peak_values)), reverse=True) # Highest first
        recent_resistances = unique_recent_resistances[:num_levels_to_return]

    recent_supports = []
    if valid_trough_indices:
        raw_recent_trough_values = df.iloc[valid_trough_indices][low_col].astype(float).tail(num_levels_to_return * 3).tolist()
        unique_recent_supports = sorted(list(set(raw_recent_trough_values))) # Lowest first
        recent_supports = unique_recent_supports[:num_levels_to_return]

    return {"supports": recent_supports, "resistances": recent_resistances}


def get_trendline_points(df: pd.DataFrame, swing_indices: list, price_col: str, trend_type: str, num_points=2):
    if not swing_indices or len(swing_indices) < num_points:
        return None, None

    valid_indices = sorted([idx for idx in swing_indices if 0 <= idx < len(df)])
    if len(valid_indices) < num_points:
        return None, None

    selected_indices = valid_indices[-num_points:]

    x_values = np.array(selected_indices)
    y_values = df.iloc[selected_indices][price_col].astype(float).values

    # Optional: Heuristic check for consistency (e.g. for uptrend, lows should generally be rising)
    # if trend_type == "uptrend_line" and num_points > 1:
    #     if not all(y_values[i] <= y_values[i+1] for i in range(len(y_values)-1)):
    #         pass # Could log a warning or filter
    # elif trend_type == "downtrend_line" and num_points > 1:
    #     if not all(y_values[i] >= y_values[i+1] for i in range(len(y_values)-1)):
    #         pass # Could log a warning or filter

    return x_values, y_values

def calculate_trendline_info(df: pd.DataFrame, swing_indices: list, price_col: str, trend_type: str):
    if df.empty or len(df) < 2:
        return {"status": "No trendline (insufficient DataFrame length)", "value": None, "slope": None}

    x_points, y_points = get_trendline_points(df, swing_indices, price_col, trend_type, num_points=2)

    if x_points is None or y_points is None or len(x_points) < 2:
        return {"status": f"No trendline (not enough valid points for {trend_type})", "value": None, "slope": None}

    if np.isnan(x_points).any() or np.isnan(y_points).any():
        return {"status": "No trendline (NaNs in points)", "value": None, "slope": None}

    if np.all(x_points == x_points[0]): # Avoid division by zero in linregress if all x are same
        return {"status": "No trendline (all x_points for regression are identical)", "value": None, "slope": None}

    try:
        slope, intercept, r_value, p_value, std_err = linregress(x_points, y_points)
    except ValueError as e:
        return {"status": f"No trendline (linregress error: {e})", "value": None, "slope": None}

    if pd.isna(slope) or pd.isna(intercept):
        return {"status": "No trendline (regression failed, NaN slope/intercept)", "value": None, "slope": None}

    x_latest = df.index[-1]
    current_trendline_value = slope * x_latest + intercept

    return {
        "status": "Trendline calculated",
        "value": round(current_trendline_value, 5),
        "slope": round(slope, 5),
        "points_used": len(x_points)
    }


def calculate_atr(df: pd.DataFrame, length=14):
    if df.empty or len(df) < length + 1: # ATR needs some lookback, +1 for safety with some TA lib versions
        # Ensure columns exist even if we can't calculate ATR
        if 'ATR' not in df.columns: df['ATR'] = np.nan
        return df, None

    df.ta.atr(length=length, append=True, col_names=('ATR',)) # Appends 'ATR_length' by default, ensure 'ATR'

    latest_atr = None
    if 'ATR' in df.columns and not df['ATR'].empty:
        latest_atr = df['ATR'].iloc[-1]
        if pd.isna(latest_atr):
            latest_atr = None
    return df, latest_atr

def identify_swing_entry(df: pd.DataFrame, trend_details: dict, num_recent_candles_to_check=1):
    entry_signal = {"entry_type": "NONE", "reason": "No entry condition met", "entry_price": None}

    if df.empty:
        entry_signal["reason"] = "DataFrame is empty for entry check."
        return entry_signal

    latest_atr = trend_details.get('latest_atr')
    if latest_atr is None or latest_atr <= 0:
        entry_signal["reason"] = "ATR not available or invalid for entry check."
        return entry_signal

    market_trend = trend_details.get('market_structure_trend')
    trendline_val = trend_details.get('trendline_value_at_latest')
    ema50_val = trend_details.get('ema50_value') # Should be passed in trend_details now

    if ema50_val is None: # Check if EMA50 value is valid
        entry_signal["reason"] = "EMA50 not available for entry check."
        return entry_signal

    proximity_threshold_factor = 0.5 # Factor of ATR
    min_abs_threshold_pips = 5 # Assuming pips, needs context of pair for actual value

    # This requires knowing pip value of symbol. For now, use a generic small float.
    # Example: For EUR/USD, 1 pip = 0.0001. 5 pips = 0.00050
    # This should ideally be symbol-specific.
    pip_size_example = 0.0001
    min_abs_threshold = min_abs_threshold_pips * pip_size_example

    proximity_threshold = max(latest_atr * proximity_threshold_factor, min_abs_threshold)

    for i in range(1, num_recent_candles_to_check + 1):
        if len(df) < i: break

        candle_idx = -i # -1 is the last completed candle
        current_low = df['low'].iloc[candle_idx]
        current_high = df['high'].iloc[candle_idx]
        current_close = df['close'].iloc[candle_idx]

        entry_reason = ""
        potential_entry_type = "NONE"

        if market_trend == "Confirmed Uptrend":
            # Check pullback to EMA50
            if current_low <= (ema50_val + proximity_threshold) and current_close > (ema50_val - proximity_threshold):
                entry_reason = f"Pullback to EMA50 (L:{current_low:.5f} vs EMA:{ema50_val:.5f})"
                potential_entry_type = "BUY"
            # Check pullback to Trendline (if available and valid)
            elif trendline_val is not None and current_low <= (trendline_val + proximity_threshold) and current_close > (trendline_val - proximity_threshold):
                entry_reason = f"Pullback to Trendline (L:{current_low:.5f} vs TL:{trendline_val:.5f})"
                potential_entry_type = "BUY"

        elif market_trend == "Confirmed Downtrend":
            # Check pullback to EMA50
            if current_high >= (ema50_val - proximity_threshold) and current_close < (ema50_val + proximity_threshold):
                entry_reason = f"Pullback to EMA50 (H:{current_high:.5f} vs EMA:{ema50_val:.5f})"
                potential_entry_type = "SELL"
            # Check pullback to Trendline (if available and valid)
            elif trendline_val is not None and current_high >= (trendline_val - proximity_threshold) and current_close < (trendline_val + proximity_threshold):
                entry_reason = f"Pullback to Trendline (H:{current_high:.5f} vs TL:{trendline_val:.5f})"
                potential_entry_type = "SELL"

        if potential_entry_type != "NONE":
            entry_signal = {"entry_type": potential_entry_type, "reason": entry_reason, "entry_price": current_close}
            break

    return entry_signal


def define_sl_tp(entry_type: str, entry_price: float, latest_atr: float,
                 ohlcv_df: pd.DataFrame, peak_indices: list, trough_indices: list,
                 risk_reward_tp1=1.5, risk_reward_tp2=2.5, atr_multiplier_sl=2.0,
                 pip_size=0.0001): # Default pip_size for forex like EURUSD

    if latest_atr is None or latest_atr <= 0: # Fallback if ATR is invalid
        # print("Warning: Invalid ATR for SL/TP calculation. Using fixed offset.")
        latest_atr = entry_price * 0.005 # 0.5% of entry price as a fallback ATR
        if latest_atr == 0 : latest_atr = 0.001 # Further fallback for zero price

    sl = None
    tp1 = None
    tp2 = None
    sl_distance_val = 0

    # Determine SL based on entry type
    if entry_type == "BUY":
        sl_atr_based = entry_price - (latest_atr * atr_multiplier_sl)
        # Use last swing low if available and it provides a tighter (but not too tight) or similar SL
        last_swing_low = None
        if trough_indices:
            valid_troughs = [idx for idx in trough_indices if 0 <= idx < len(ohlcv_df)]
            if valid_troughs:
                last_swing_low_val = ohlcv_df['low'].iloc[valid_troughs[-1]]
                # Place SL slightly below the last swing low
                last_swing_low = last_swing_low_val - (latest_atr * 0.2)

        if last_swing_low is not None:
            sl = min(sl_atr_based, last_swing_low) # Choose the more conservative (lower) SL
        else:
            sl = sl_atr_based

        # Ensure SL is meaningfully different from entry_price
        if entry_price - sl < pip_size * 5: # Min 5 pips SL
            sl = entry_price - (pip_size * 10) # Fallback to 10 pips if calculated SL is too close

        sl_distance_val = entry_price - sl
        if sl_distance_val <= 0 : # Should not happen with BUY if sl < entry_price
            sl_distance_val = latest_atr * atr_multiplier_sl # Fallback SL distance
            sl = entry_price - sl_distance_val

        tp1 = entry_price + sl_distance_val * risk_reward_tp1
        tp2 = entry_price + sl_distance_val * risk_reward_tp2

    elif entry_type == "SELL":
        sl_atr_based = entry_price + (latest_atr * atr_multiplier_sl)
        last_swing_high = None
        if peak_indices:
            valid_peaks = [idx for idx in peak_indices if 0 <= idx < len(ohlcv_df)]
            if valid_peaks:
                last_swing_high_val = ohlcv_df['high'].iloc[valid_peaks[-1]]
                last_swing_high = last_swing_high_val + (latest_atr * 0.2)

        if last_swing_high is not None:
            sl = max(sl_atr_based, last_swing_high) # Choose more conservative (higher) SL
        else:
            sl = sl_atr_based

        if sl - entry_price < pip_size * 5: # Min 5 pips SL
            sl = entry_price + (pip_size * 10)

        sl_distance_val = sl - entry_price
        if sl_distance_val <= 0:
            sl_distance_val = latest_atr * atr_multiplier_sl
            sl = entry_price + sl_distance_val

        tp1 = entry_price - sl_distance_val * risk_reward_tp1
        tp2 = entry_price - sl_distance_val * risk_reward_tp2

    # Round to 5 decimal places (typical for forex)
    precision = 5
    return {
        "sl": round(sl, precision) if sl is not None else None,
        "tp1": round(tp1, precision) if tp1 is not None else None,
        "tp2": round(tp2, precision) if tp2 is not None else None,
        "sl_distance": round(sl_distance_val, precision) if sl_distance_val > 0 else None
    }

def formulate_trade_signal(symbol: str, entry_signal_details: dict, sl_tp_details: dict,
                           market_trend: str, lot_size: float,
                           default_pip_size=0.0001, # For most non-JPY forex pairs
                           default_pip_value_for_std_lot=10.0): # USD value for 1 pip, 1 std lot

    if not entry_signal_details or entry_signal_details.get("entry_type") == "NONE":
        return f"❌ No valid setup found for {symbol}. Reason: {entry_signal_details.get('reason', 'N/A')}"

    entry_type = entry_signal_details["entry_type"]
    entry_price = entry_signal_details["entry_price"]
    entry_reason = entry_signal_details.get("reason", "") # Added .get for safety

    sl = sl_tp_details.get("sl")
    tp1 = sl_tp_details.get("tp1")
    tp2 = sl_tp_details.get("tp2") # Keep tp2 for R:R display
    sl_distance = sl_tp_details.get("sl_distance")

    if None in [entry_price, sl, tp1, tp2, sl_distance] or sl_distance <= 0:
         return f"❌ No valid setup for {symbol}. Reason: SL/TP calculation failed. SL Dist: {sl_distance}"

    rr_tp1 = abs(tp1 - entry_price) / sl_distance if sl_distance > 0 else 0
    rr_tp2 = abs(tp2 - entry_price) / sl_distance if sl_distance > 0 else 0

    signal_icon = "🔔"
    signal_str = (
        f"{signal_icon} {entry_type} {symbol}\n"
        f"Trend: {market_trend}\n"
        f"Entry: {entry_price:.5f} (Reason: {entry_reason})\n"
        f"SL: {sl:.5f}\n"
        f"TP1: {tp1:.5f} (R:R ~1:{rr_tp1:.1f})\n"
        f"TP2: {tp2:.5f} (R:R ~1:{rr_tp2:.1f})" # Removed extra R:R line
        # f"Risk/Reward (TP2): ~1:{rr_tp2:.1f}" # This was redundant
    )

    # Simplified PnL Estimation
    # Assumes pip size for symbol (e.g. 0.0001 for EURUSD, 0.01 for USDJPY)
    # Assumes pip value for 1 standard lot (e.g. $10 for EURUSD)
    # This is a simplification. Real pip value varies by pair and account currency.

    # Adjust pip_size for JPY pairs for more sensible PnL estimation
    current_pip_size = 0.01 if "JPY" in symbol.upper() else default_pip_size

    sl_pips = sl_distance / current_pip_size
    tp1_pips = abs(tp1 - entry_price) / current_pip_size

    # PnL = pips * value_per_pip_per_lot * lot_size
    # value_per_pip_per_lot = default_pip_value_for_std_lot
    estimated_pnl_tp1 = tp1_pips * default_pip_value_for_std_lot * lot_size
    estimated_loss_sl = sl_pips * default_pip_value_for_std_lot * lot_size

    pnl_str = (
        f"\nEst. PnL ({lot_size} lot): TP1 ~${estimated_pnl_tp1:.0f}, SL ~-${estimated_loss_sl:.0f}"
    )
    signal_str += pnl_str

    return signal_str
