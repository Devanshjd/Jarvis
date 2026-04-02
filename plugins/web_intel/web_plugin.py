"""
J.A.R.V.I.S — Web Intelligence Plugin
Real-time data from free public APIs.

Commands:
    /weather <city>     — Current weather & forecast
    /news [topic]       — Top headlines
    /wiki <topic>       — Wikipedia summary
    /define <word>      — Dictionary definition
    /translate <text>   — Translate text (auto-detect → English, or specify)
    /crypto [coin]      — Crypto prices (BTC, ETH, etc.)
    /currency <amount> <from> <to> — Currency conversion
    /quote              — Inspirational quote
    /joke               — Random joke
    /fact               — Random fun fact
    /ip [address]       — IP geolocation & network info
    /nasa               — NASA Astronomy Picture of the Day

All APIs are FREE — most need zero API keys.
"""

import threading
import json
import urllib.request
import urllib.parse
import urllib.error

from core.plugin_manager import PluginBase


def _fetch(url: str, timeout: int = 10) -> dict | str:
    """Fetch JSON or text from a URL."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "JARVIS/5.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data


def _bg(func, jarvis, *args):
    """Run a function in background thread, post result to chat.
    Passes jarvis as first arg to the function, then *args after."""
    def _run():
        try:
            result = func(jarvis, *args)
            jarvis.root.after(0, lambda: jarvis.chat.add_message("assistant", result))
            jarvis.root.after(0, lambda: jarvis.plugin_manager.on_response(result))
        except Exception as e:
            jarvis.root.after(0, lambda: jarvis.chat.add_message(
                "system", f"API error: {e}"))
    threading.Thread(target=_run, daemon=True).start()


class WebIntelPlugin(PluginBase):
    name = "web_intel"
    description = "Real-time web intelligence — weather, news, crypto, wiki, translate"
    version = "1.0"

    def activate(self):
        pass

    def deactivate(self):
        pass

    def on_command(self, command: str, args: str) -> bool:
        cmd = command.lower()
        if cmd == "/weather":
            self._show_status("Checking weather...")
            _bg(self.get_weather, self.jarvis, args or "auto")
            return True
        if cmd == "/news":
            self._show_status("Fetching headlines...")
            _bg(self.get_news, self.jarvis, args)
            return True
        if cmd == "/wiki":
            self._show_status(f"Searching Wikipedia...")
            _bg(self.get_wiki, self.jarvis, args)
            return True
        if cmd == "/define":
            self._show_status(f"Looking up definition...")
            _bg(self.get_definition, self.jarvis, args)
            return True
        if cmd == "/translate":
            self._show_status("Translating...")
            _bg(self.get_translation, self.jarvis, args)
            return True
        if cmd == "/crypto":
            self._show_status("Fetching crypto prices...")
            _bg(self.get_crypto, self.jarvis, args)
            return True
        if cmd == "/currency":
            self._show_status("Converting currency...")
            _bg(self.get_currency, self.jarvis, args)
            return True
        if cmd == "/quote":
            self._show_status("Finding inspiration...")
            _bg(self.get_quote, self.jarvis)
            return True
        if cmd == "/joke":
            _bg(self.get_joke, self.jarvis)
            return True
        if cmd == "/fact":
            _bg(self.get_fact, self.jarvis)
            return True
        if cmd == "/ip":
            self._show_status("Looking up IP...")
            _bg(self.get_ip_info, self.jarvis, args)
            return True
        if cmd == "/nasa":
            self._show_status("Contacting NASA...")
            _bg(self.get_nasa_apod, self.jarvis)
            return True
        return False

    def _show_status(self, msg: str):
        self.jarvis.chat.add_message("system", msg)

    # ══════════════════════════════════════════════════════════════
    # WEATHER (wttr.in — no API key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_weather(jarvis, city: str) -> str:
        if not city or city == "auto":
            # Auto-detect location from IP
            try:
                loc = _fetch("https://ipapi.co/json/")
                city = loc.get("city", "London")
            except Exception:
                city = "London"

        city_encoded = urllib.parse.quote(city)
        data = _fetch(f"https://wttr.in/{city_encoded}?format=j1")

        current = data["current_condition"][0]
        temp_c = current["temp_C"]
        feels = current["FeelsLikeC"]
        desc = current["weatherDesc"][0]["value"]
        humidity = current["humidity"]
        wind = current["windspeedKmph"]
        wind_dir = current["winddir16Point"]

        # Today's forecast
        today = data["weather"][0]
        max_t = today["maxtempC"]
        min_t = today["mintempC"]

        # Tomorrow
        tomorrow = data["weather"][1] if len(data["weather"]) > 1 else None

        result = (
            f"Weather Report — {city.title()}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Currently: {desc}, {temp_c}°C (feels like {feels}°C)\n"
            f"Humidity: {humidity}% · Wind: {wind} km/h {wind_dir}\n"
            f"Today: {min_t}°C — {max_t}°C\n"
        )
        if tomorrow:
            tm_desc = tomorrow["hourly"][4]["weatherDesc"][0]["value"]
            result += f"Tomorrow: {tomorrow['mintempC']}°C — {tomorrow['maxtempC']}°C, {tm_desc}\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # NEWS (using Google News RSS as fallback — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_news(jarvis, topic: str = "") -> str:
        # Use wttr-style simple news from a free source
        if topic:
            url = f"https://gnews.io/api/v4/search?q={urllib.parse.quote(topic)}&lang=en&max=5&apikey=demo"
        else:
            url = "https://gnews.io/api/v4/top-headlines?lang=en&max=5&apikey=demo"

        try:
            data = _fetch(url)
            articles = data.get("articles", [])
        except Exception:
            # Fallback: try a different free news source
            try:
                url = f"https://ok.surf/api/v1/cors/news-feed"
                data = _fetch(url)
                # Format whatever we get
                if isinstance(data, dict):
                    articles = []
                    for source, items in list(data.items())[:3]:
                        for item in items[:2]:
                            articles.append({
                                "title": item.get("title", ""),
                                "source": {"name": source},
                                "description": "",
                            })
                else:
                    return "News services temporarily unavailable, sir."
            except Exception:
                return "Unable to fetch news at the moment, sir. Try again shortly."

        if not articles:
            return "No news articles found, sir."

        result = f"Latest Headlines{' — ' + topic.title() if topic else ''}\n"
        result += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for i, a in enumerate(articles[:5], 1):
            title = a.get("title", "No title")
            source = a.get("source", {}).get("name", "Unknown")
            result += f"{i}. {title}\n   — {source}\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # WIKIPEDIA (no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_wiki(jarvis, topic: str) -> str:
        if not topic:
            return "What would you like me to look up, sir? Usage: /wiki <topic>"

        topic_encoded = urllib.parse.quote(topic)
        data = _fetch(f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic_encoded}")

        if data.get("type") == "disambiguation":
            return f"'{topic}' has multiple meanings. Could you be more specific, sir?"

        title = data.get("title", topic)
        extract = data.get("extract", "No information found.")

        # Trim to reasonable length
        if len(extract) > 800:
            cut = extract[:800]
            last_period = cut.rfind(".")
            if last_period > 400:
                extract = cut[:last_period + 1]
            else:
                extract = cut + "..."

        return f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n{extract}"

    # ══════════════════════════════════════════════════════════════
    # DICTIONARY (no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_definition(jarvis, word: str) -> str:
        if not word:
            return "Which word, sir? Usage: /define <word>"

        word = word.strip().split()[0].lower()
        data = _fetch(f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}")

        if isinstance(data, list) and data:
            entry = data[0]
            word_title = entry.get("word", word)
            phonetic = entry.get("phonetic", "")

            result = f"{word_title}"
            if phonetic:
                result += f"  {phonetic}"
            result += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"

            for meaning in entry.get("meanings", [])[:3]:
                pos = meaning.get("partOfSpeech", "")
                result += f"\n({pos})\n"
                for defn in meaning.get("definitions", [])[:2]:
                    result += f"  • {defn['definition']}\n"
                    if defn.get("example"):
                        result += f"    Example: \"{defn['example']}\"\n"

            synonyms = []
            for m in entry.get("meanings", []):
                synonyms.extend(m.get("synonyms", [])[:3])
            if synonyms:
                result += f"\nSynonyms: {', '.join(synonyms[:6])}"

            return result
        else:
            return f"No definition found for '{word}', sir."

    # ══════════════════════════════════════════════════════════════
    # TRANSLATION (MyMemory — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_translation(jarvis, text: str) -> str:
        if not text:
            return "Usage: /translate <text> or /translate en|hi <text>"

        # Check if language pair specified (e.g., "en|hi hello world")
        parts = text.split(None, 1)
        if len(parts) > 1 and "|" in parts[0]:
            langpair = parts[0]
            text_to_translate = parts[1]
        else:
            # Default: auto-detect to English
            langpair = "autodetect|en"
            text_to_translate = text

        encoded = urllib.parse.quote(text_to_translate)
        data = _fetch(
            f"https://api.mymemory.translated.net/get?q={encoded}&langpair={langpair}"
        )

        translated = data.get("responseData", {}).get("translatedText", "")
        if translated and translated.lower() != text_to_translate.lower():
            lang_detected = data.get("responseData", {}).get("detectedLanguage", "")
            result = f"Translation ({langpair})\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            result += f"Original: {text_to_translate}\nTranslated: {translated}"
            return result
        else:
            return f"Could not translate: {text_to_translate}"

    # ══════════════════════════════════════════════════════════════
    # CRYPTO (CoinGecko — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_crypto(jarvis, coin: str = "") -> str:
        if not coin:
            coin = "bitcoin,ethereum,dogecoin,solana"
        else:
            # Map common abbreviations
            coin_map = {
                "btc": "bitcoin", "eth": "ethereum", "doge": "dogecoin",
                "sol": "solana", "ada": "cardano", "xrp": "ripple",
                "dot": "polkadot", "bnb": "binancecoin", "matic": "matic-network",
                "avax": "avalanche-2", "link": "chainlink", "ltc": "litecoin",
            }
            coins = [coin_map.get(c.strip().lower(), c.strip().lower())
                     for c in coin.split(",")]
            coin = ",".join(coins)

        data = _fetch(
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin}&vs_currencies=usd,inr"
            f"&include_24hr_change=true&include_market_cap=true"
        )

        if not data:
            return "Could not fetch crypto prices, sir."

        result = "Crypto Prices\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for name, info in data.items():
            usd = info.get("usd", 0)
            inr = info.get("inr", 0)
            change = info.get("usd_24h_change", 0)
            arrow = "▲" if change >= 0 else "▼"
            result += (
                f"{name.title()}: ${usd:,.2f} (₹{inr:,.0f})\n"
                f"  24h: {arrow} {abs(change):.1f}%\n"
            )

        return result

    # ══════════════════════════════════════════════════════════════
    # CURRENCY (Frankfurter — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_currency(jarvis, args: str) -> str:
        if not args:
            return "Usage: /currency 100 USD INR"

        parts = args.upper().split()
        if len(parts) < 3:
            return "Usage: /currency <amount> <from> <to>\nExample: /currency 100 USD INR"

        try:
            amount = float(parts[0])
        except ValueError:
            return "Invalid amount. Usage: /currency 100 USD INR"

        from_curr = parts[1]
        to_curr = parts[2]

        data = _fetch(
            f"https://api.frankfurter.app/latest"
            f"?from={from_curr}&to={to_curr}&amount={amount}"
        )

        if "rates" in data:
            result = f"Currency Conversion\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for curr, val in data["rates"].items():
                result += f"{amount:,.2f} {from_curr} = {val:,.2f} {curr}\n"
            return result
        else:
            return f"Could not convert {from_curr} to {to_curr}, sir."

    # ══════════════════════════════════════════════════════════════
    # QUOTES (ZenQuotes — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_quote(jarvis) -> str:
        data = _fetch("https://zenquotes.io/api/random")
        if isinstance(data, list) and data:
            q = data[0]
            return f"\"{q.get('q', '')}\"\n  — {q.get('a', 'Unknown')}"
        return "Unable to fetch a quote at the moment, sir."

    # ══════════════════════════════════════════════════════════════
    # JOKES (JokeAPI — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_joke(jarvis) -> str:
        data = _fetch("https://v2.jokeapi.dev/joke/Any?safe-mode&type=single,twopart")

        if data.get("type") == "single":
            return data.get("joke", "I seem to have forgotten the joke, sir.")
        elif data.get("type") == "twopart":
            return f"{data.get('setup', '')}\n\n{data.get('delivery', '')}"
        return "My humor module appears to be offline, sir."

    # ══════════════════════════════════════════════════════════════
    # FUN FACTS (no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_fact(jarvis) -> str:
        data = _fetch("https://uselessfacts.jsph.pl/api/v2/facts/random")
        return data.get("text", "Fact retrieval failed, sir.")

    # ══════════════════════════════════════════════════════════════
    # IP GEOLOCATION (ipapi.co — no key needed)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_ip_info(jarvis, ip: str = "") -> str:
        if ip and ip.strip():
            url = f"https://ipapi.co/{ip.strip()}/json/"
        else:
            url = "https://ipapi.co/json/"

        data = _fetch(url)

        if data.get("error"):
            return f"Could not look up IP: {data.get('reason', 'unknown error')}"

        result = (
            f"IP Intelligence Report\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"IP: {data.get('ip', 'N/A')}\n"
            f"Location: {data.get('city', '?')}, {data.get('region', '?')}, {data.get('country_name', '?')}\n"
            f"Coordinates: {data.get('latitude', '?')}, {data.get('longitude', '?')}\n"
            f"Timezone: {data.get('timezone', '?')}\n"
            f"ISP: {data.get('org', 'N/A')}\n"
            f"ASN: {data.get('asn', 'N/A')}\n"
            f"Network: {data.get('network', 'N/A')}\n"
            f"Currency: {data.get('currency_name', '?')} ({data.get('currency', '?')})\n"
        )
        return result

    # ══════════════════════════════════════════════════════════════
    # NASA APOD (free with demo key)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def get_nasa_apod(jarvis) -> str:
        data = _fetch("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY")

        title = data.get("title", "Unknown")
        date = data.get("date", "")
        explanation = data.get("explanation", "")

        if len(explanation) > 500:
            cut = explanation[:500]
            last_period = cut.rfind(".")
            if last_period > 200:
                explanation = cut[:last_period + 1]
            else:
                explanation = cut + "..."

        return (
            f"NASA — Astronomy Picture of the Day\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{title} ({date})\n\n"
            f"{explanation}"
        )

    # ══════════════════════════════════════════════════════════════
    # NATURAL LANGUAGE DETECTION
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str) -> str | None:
        """Detect natural language queries for web intel."""
        msg = message.lower().strip()

        # Weather patterns
        if any(msg.startswith(p) for p in [
            "what's the weather", "whats the weather", "how's the weather",
            "weather in ", "weather for ", "temperature in ",
        ]):
            city = msg.split("in ")[-1].split("for ")[-1].strip() if " in " in msg or " for " in msg else ""
            self._show_status("Checking weather...")
            _bg(self.get_weather, self.jarvis, city)
            return "__handled__"

        # Crypto patterns
        if any(p in msg for p in ["bitcoin price", "crypto price", "eth price", "btc price"]):
            self._show_status("Fetching crypto...")
            _bg(self.get_crypto, self.jarvis, "")
            return "__handled__"

        return None

    def get_status(self) -> dict:
        return {"name": self.name, "active": True}
