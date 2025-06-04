// In space_zero_bot/static/script.js
document.addEventListener('DOMContentLoaded', function() {
    const tradingPairSelect = document.getElementById('trading-pair');
    const lotSizeInput = document.getElementById('lot-size');
    const getSignalBtn = document.getElementById('get-signal-btn');
    const signalOutput = document.getElementById('signal-output');

    // ... (loadTradingPairs function from Step 7 should be here) ...
    async function loadTradingPairs() {
        try {
            // ... (implementation from Step 7)
            const response = await fetch('/api/trading_pairs');
            if (!response.ok) {
                let errorMsg = `Error fetching trading pairs: ${response.status} ${response.statusText}`;
                try {
                    const errData = await response.json();
                    errorMsg = errData.error || errorMsg;
                } catch (e) { /* Ignore if no JSON body */ }

                console.error(errorMsg);
                tradingPairSelect.innerHTML = `<option value="">Error loading pairs</option>`;
                if(signalOutput) signalOutput.textContent = errorMsg;
                return;
            }

            const pairs = await response.json();

            if (!pairs || pairs.length === 0 || (pairs.error && pairs.error.includes("Could not fetch trading pairs"))) {
                tradingPairSelect.innerHTML = '<option value="">No pairs available</option>';
                if(pairs.error && signalOutput) signalOutput.textContent = pairs.error;
                return;
            }

            tradingPairSelect.innerHTML = '';
            pairs.forEach(pair => {
                const option = new Option(pair.display_name, pair.symbol);
                tradingPairSelect.add(option);
            });

        } catch (error) {
            console.error('Failed to load trading pairs:', error);
            tradingPairSelect.innerHTML = '<option value="">Failed to load pairs</option>';
            if(signalOutput) signalOutput.textContent = 'Network error or server issue while fetching trading pairs.';
        }
    }
    if(tradingPairSelect) loadTradingPairs(); // Ensure it runs only if element exists


    if (getSignalBtn) {
        getSignalBtn.addEventListener('click', async function() {
            const selectedPair = tradingPairSelect.value;
            const currentLotSize = lotSizeInput.value;

            if (!selectedPair) {
                signalOutput.textContent = 'Please select a trading pair.';
                return;
            }
            if (!currentLotSize || parseFloat(currentLotSize) <= 0) {
                signalOutput.textContent = 'Please enter a valid positive lot size.';
                return;
            }

            signalOutput.textContent = '⏳ Getting signal...';
            getSignalBtn.disabled = true;

            try {
                const response = await fetch('/api/get_signal', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        symbol: selectedPair,
                        lot_size: currentLotSize  // Will be parsed to float on backend
                    }),
                });

                const data = await response.json(); // Try to parse JSON regardless of response.ok for error messages

                if (!response.ok) {
                    // data.error should be populated by Flask's jsonify({"error": ...})
                    signalOutput.textContent = `Error: ${data.error || response.statusText || 'Unknown error'}`;
                } else {
                    // Assuming final_signal contains
 for newlines, and CSS handles it with white-space: pre-wrap;
                    signalOutput.textContent = data.final_signal;
                    // Optional: Log detailed analysis for debugging
                    // console.log("Detailed Analysis H4:", data.detailed_analysis_H4);
                }

            } catch (error) {
                console.error('Error fetching signal:', error);
                signalOutput.textContent = `Network error or server not responding: ${error.message}`;
            } finally {
                getSignalBtn.disabled = false;
            }
        });
    }
});
