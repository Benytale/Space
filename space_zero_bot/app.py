from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import asyncio
from deriv_api import DerivAPI
import pandas as pd
import pandas_ta as ta
from . import signal_logic  # Assuming signal_logic.py is in the same directory

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'supersecretkey_pleasereplaceme'  # Replace with a real secret key

SHARED_PASSWORD = "spacezero2025"
DERIV_APP_ID = 1  # Placeholder app ID

async def fetch_deriv_active_symbols():
    api = None
    try:
        api = DerivAPI(app_id=DERIV_APP_ID)
        response = await api.active_symbols({
            "active_symbols": "brief",
            "product_type": "basic"
        })

        symbols = []
        if response and 'active_symbols' in response:
            for asset in response['active_symbols']:
                if asset.get('market') == 'forex' and asset.get('pip'):
                    symbols.append({
                        'symbol': asset.get('symbol'),
                        'display_name': asset.get('display_name')
                    })
        symbols.sort(key=lambda x: x['display_name'])
        return symbols
    except Exception as e:
        print(f"Error fetching Deriv symbols: {e}")
        return []
    finally:
        if api:
            await api.disconnect()

@app.route('/api/trading_pairs')
def trading_pairs_route():
    if not session.get('authenticated'):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        symbols = asyncio.run(fetch_deriv_active_symbols())
        return jsonify(symbols) if symbols else jsonify({"error": "No pairs available"}), 500
    except Exception as e:
        app.logger.error(f"Exception in /api/trading_pairs: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/')
def home():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == SHARED_PASSWORD:
            session['authenticated'] = True
            session.permanent = True
            return redirect(url_for('home'))
        error = "Invalid password. Please try again."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

async def fetch_ohlcv_data(api_instance, symbol, timeframe_seconds, count):
    try:
        response = await api_instance.ticks_history({
            "ticks_history": symbol,
            "style": "candles",
            "granularity": timeframe_seconds,
            "count": count,
            "end": "latest",
        })

        if response and 'history' in response and 'candles' in response['history']:
            df = pd.DataFrame(response['history']['candles'])
            if df.empty:
                return pd.DataFrame()

            required_cols = {'epoch', 'open', 'high', 'low', 'close'}
            if not required_cols.issubset(df.columns):
                return pd.DataFrame()

            df['time'] = pd.to_datetime(df['epoch'], unit='s')
            df = df[['time', 'open', 'high', 'low', 'close']]
            if 'volume' not in df.columns:
                df['volume'] = 0

            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching OHLCV for {symbol}: {e}")
        return pd.DataFrame()

@app.route('/api/get_signal', methods=['POST'])
async def get_signal_route():
    if not session.get('authenticated'):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    symbol = data.get('symbol')
    lot_size_str = data.get('lot_size')
    
    if not symbol or not lot_size_str:
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        lot_size = float(lot_size_str)
        if lot_size <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Invalid lot size"}), 400

    api = None
    analysis_results = {"H4": {}}
    ohlcv_df_h4 = pd.DataFrame()

    try:
        api = DerivAPI(app_id=DERIV_APP_ID)
        ohlcv_df_h4 = await fetch_ohlcv_data(api, symbol, 14400, 300)
        
        if ohlcv_df_h4.empty:
            return jsonify({"error": f"No H4 data for {symbol}"}), 500

        analysis_results["H4"]['data_fetched'] = f"{len(ohlcv_df_h4)} candles"
        
        if 'close' in ohlcv_df_h4.columns and len(ohlcv_df_h4) >= 50:
            # Perform technical analysis (EMA, peaks/troughs, trend analysis)
            ohlcv_df_h4.ta.ema(length=50, append=True, col_names=('EMA_50',))
            ohlcv_df_h4.ta.ema(length=200, append=True, col_names=('EMA_200',))
            ema_trend = signal_logic.determine_trend_from_emas(ohlcv_df_h4)
            
            peak_idx, trough_idx = signal_logic.detect_peaks_troughs(ohlcv_df_h4)
            structure_trend = signal_logic.confirm_trend_with_market_structure(
                ohlcv_df_h4, ema_trend, peak_idx, trough_idx
            )
            
            # Store analysis results
            analysis_results["H4"].update({
                'ema_trend': ema_trend,
                'market_structure_trend': structure_trend,
                'sr_levels': signal_logic.identify_sr_levels(ohlcv_df_h4, peak_idx, trough_idx, 5),
                'entry_signal': {"entry_type": "NONE", "reason": "No signal generated"}
            })
            
            # Generate entry signal if valid trend exists
            if structure_trend in ["Confirmed Uptrend", "Confirmed Downtrend"]:
                _, latest_atr = signal_logic.calculate_atr(ohlcv_df_h4.copy())
                ema50 = ohlcv_df_h4['EMA_50'].iloc[-1] if 'EMA_50' in ohlcv_df_h4 else None
                
                if latest_atr and ema50:
                    trend_details = {
                        "market_structure_trend": structure_trend,
                        "latest_atr": latest_atr,
                        "ema50_value": ema50
                    }
                    analysis_results["H4"]['entry_signal'] = signal_logic.identify_swing_entry(
                        ohlcv_df_h4, trend_details
                    )
    except Exception as e:
        app.logger.error(f"Analysis error for {symbol}: {e}", exc_info=True)
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500
    finally:
        if api:
            await api.disconnect()

    # Generate final trade signal
    entry_signal = analysis_results["H4"].get('entry_signal', {})
    if entry_signal.get("entry_type") != "NONE":
        sl_tp_details = signal_logic.define_sl_tp(
            entry_signal["entry_type"],
            entry_signal["entry_price"],
            analysis_results["H4"].get('latest_atr', 0.001),
            ohlcv_df_h4,
            analysis_results["H4"].get('peak_indices', []),
            analysis_results["H4"].get('trough_indices', []),
            0.0001
        )
        if sl_tp_details.get("sl") is not None:
            final_signal = signal_logic.formulate_trade_signal(
                symbol, entry_signal, sl_tp_details, 
                analysis_results["H4"].get('market_structure_trend', 'N/A'), 
                lot_size
            )
        else:
            final_signal = f"❌ SL/TP calc failed for {symbol}"
    else:
        reason = entry_signal.get('reason', 'No valid setup')
        final_signal = f"❌ No setup for {symbol}: {reason}"

    return jsonify({
        "symbol": symbol,
        "lot_size": lot_size,
        "final_signal": final_signal,
        "detailed_analysis_H4": analysis_results.get("H4")
    })

if __name__ == '__main__':
    app.run(debug=True)
