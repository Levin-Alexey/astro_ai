// Преобразовано для запуска в Node.js: используем axios вместо $.ajax
const axios = require('axios');
const api = 'natal_transits/daily';
const userId = '647875';
const apiKey = 'c74d0730f069f4fb6c5cd5db70e24da9a1cc1a9f';
const language = 'en'; // По умолчанию en
const data = {
  day: 26,
  month: 7,
  year: 2000,
  hour: 10,
  min: 38,
  lat: 56.132,
  lon: 60.342,
  tzone: 6.0,
};

const auth = "Basic " + Buffer.from(userId + ":" + apiKey).toString("base64");
const url = "https://json.astrologyapi.com/v1/" + api;

(async () => {
  try {
    const resp = await axios.post(url, data, {
      headers: {
        Authorization: auth,
        'Content-Type': 'application/json',
        'Accept-Language': language,
      },
      timeout: 15000,
    });
    console.log('Response:');
    console.log(typeof resp.data === 'object' ? JSON.stringify(resp.data, null, 2) : resp.data);
  } catch (err) {
    if (err.response) {
      console.error('HTTP Error:', err.response.status, err.response.statusText);
      try {
        console.error(JSON.stringify(err.response.data, null, 2));
      } catch (e) {
        console.error(err.response.data);
      }
    } else if (err.request) {
      console.error('No response received:', err.message);
    } else {
      console.error('Error:', err.message);
    }
    process.exitCode = 1;
  }
})();
