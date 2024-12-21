import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.arima.model import ARIMA
import logging

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALPHA_VANTAGE_API_KEY = 'SWLSWOARGQT9EKG0'

def fetch_stock_data(symbol):
    logger.info(f"Fetching stock data for symbol: {symbol}")
    try:
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if "Error Message" in data:
            raise ValueError(data["Error Message"])

        if "Time Series (Daily)" not in data:
            if "Note" in data:
                raise ValueError(f"API Limit Reached: {data['Note']}")
            raise ValueError("No daily time series found in the response")

        df = pd.DataFrame(data["Time Series (Daily)"]).T
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df = df.rename(columns={'4. close': 'Close'})
        return df[['Close']].sort_index()

    except Exception as e:
        logger.error(f"Error in fetch_stock_data: {str(e)}")
        raise

def fetch_forex_data(from_currency='EUR', to_currency='USD'):
    logger.info(f"Fetching forex data for {from_currency}/{to_currency}")
    try:
        url = f'https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_currency}&to_symbol={to_currency}&apikey={ALPHA_VANTAGE_API_KEY}'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if "Error Message" in data:
            raise ValueError(data["Error Message"])

        if "Time Series FX (Daily)" not in data:
            if "Note" in data:
                raise ValueError(f"API Limit Reached: {data['Note']}")
            raise ValueError("No daily forex time series found in the response")

        df = pd.DataFrame(data["Time Series FX (Daily)"]).T
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df = df.rename(columns={'4. close': 'Close'})
        return df[['Close']].sort_index()

    except Exception as e:
        logger.error(f"Error in fetch_forex_data: {str(e)}")
        raise

def detect_anomalies(stock_data):
    try:
        stock_data['Rolling_Mean'] = stock_data['Close'].rolling(window=5).mean()
        stock_data['Rolling_Std'] = stock_data['Close'].rolling(window=5).std()
        stock_data.dropna(inplace=True)

        iso_forest = IsolationForest(contamination=0.01, random_state=42)
        stock_data['Anomaly'] = iso_forest.fit_predict(stock_data[['Close', 'Rolling_Mean', 'Rolling_Std']])
        stock_data['Anomaly'] = stock_data['Anomaly'].apply(lambda x: 1 if x == -1 else 0)

        return stock_data

    except Exception as e:
        logger.error(f"Error in detect_anomalies: {str(e)}")
        raise

def currency_forecast(currency_data, forecast_steps=10):
    try:
        arima_model = ARIMA(currency_data['Close'], order=(5, 1, 0))
        arima_fit = arima_model.fit()

        currency_forecast = arima_fit.forecast(steps=forecast_steps)
        forecast_dates = pd.date_range(currency_data.index[-1], periods=forecast_steps + 1, freq='D')[1:]
        currency_forecast_df = pd.DataFrame({'Date': forecast_dates, 'Forecasted_Price': currency_forecast})
        currency_forecast_df.set_index('Date', inplace=True)

        return currency_forecast_df

    except Exception as e:
        logger.error(f"Error in currency_forecast: {str(e)}")
        raise

@app.route('/api/market-data', methods=['POST'])
def get_market_data():
    try:
        data = request.get_json()
        if not data or 'stock_symbol' not in data:
            return jsonify({'error': 'Missing stock_symbol in request'}), 400

        stock_symbol = data['stock_symbol'].upper()
        logger.info(f"Processing request for stock symbol: {stock_symbol}")

        stock_data = fetch_stock_data(stock_symbol)
        currency_data = fetch_forex_data()

        stock_data_with_anomalies = detect_anomalies(stock_data)
        currency_forecast_df = currency_forecast(currency_data)

        response_data = {
            'stock_data': stock_data_with_anomalies.reset_index().to_dict(orient='records'),
            'currency_data': currency_data.reset_index().to_dict(orient='records'),
            'currency_forecast': currency_forecast_df.reset_index().to_dict(orient='records')
        }

        logger.info("Successfully prepared response")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

