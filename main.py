import fitz  # PyMuPDF
import os
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google import genai

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

def get_authenticated_service():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    credentials = flow.run_local_server(port=0)
    return build("youtube", "v3", credentials=credentials)

def create_playlist(youtube, title, description="Automatisch generierte Lernplaylist"):
    request = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description
            },
            "status": {
                "privacyStatus": "private"
            }
        }
    )
    response = request.execute()
    print(f"🎞️ Neue Playlist erstellt: {response['id']}")
    return response["id"]

def add_video_to_playlist(youtube, playlist_id, video_id):
    request = youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
    )
    request.execute()

def extract_video_id(url):
    import re
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None

def add_all_videos_to_playlist(youtube, video_mapping, playlist_name="Lernvideos"):
    playlist_id = create_playlist(youtube, playlist_name)

    for eintrag in video_mapping:
        video_id = extract_video_id(eintrag.get("url", ""))
        if video_id:
            add_video_to_playlist(youtube, playlist_id, video_id)
            print(f"➕ Hinzugefügt: {eintrag['theme']} ({video_id})")
        else:
            print(f"⚠️ Ungültige URL: {eintrag.get('url', '')}")
#enter own API key
client = genai.Client(api_key="APIKEY")

def read_all_pdfs_from_folder(folder_path):
    contents = ""
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(folder_path, filename)
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    contents += page.get_text()
    return contents

def extract_themes_from_folder(folder_path, chunk_size=8000, delay_between_calls=1.5):
    print(f"\n📄 Lese PDF-Dateien aus dem Ordner: {folder_path}")
    full_text = read_all_pdfs_from_folder(folder_path)
    themes = []

    for i in range(0, len(full_text), chunk_size):
        print(f"🧩 Verarbeite Chunk {i//chunk_size + 1} von {len(full_text) // chunk_size + 1}")
        chunk = full_text[i:i + chunk_size]
        try:
            result = extract_themes_from_text(chunk)
            themes.append(result)
            time.sleep(delay_between_calls)  # Gemini rate limiting beachten
        except Exception as e:
            print(f"Fehler bei Chunk {i//chunk_size + 1}: {e}")
            continue

    return themes

def find_and_evaluate_videos_for_themes(themenliste, max_videos_per_theme=3):
    import re
    results = []
    for thema in themenliste:
        print(f"\n🔍 Suche nach Videos zu: {thema}")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"Suche auf YouTube nach {max_videos_per_theme} hochwertigen Videos zum Thema '{thema}' für ein Informatikstudium. "
                f"Gib nur eine Liste von YouTube-URLs zurück."
            )
        )
        urls = re.findall(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}", response.text)
        if not urls:
            print(f"⚠️ Keine gültigen YouTube-Links gefunden für: {thema}")
            continue
        for url in urls:
            bewertung = evaluate_video_quality(url, thema)
            print(f"📺 {url}\n💬 Bewertung: {bewertung}\n")
            results.append({
                "theme": thema,
                "url": url.strip(),
                "review": bewertung
            })
    print(f"✅ Themenliste abgeschlossen. {len(themenliste)} Themen verarbeitet.")
    return results

def extract_themes_from_text(folien_text):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=(
            "Du bist ein Universitätsassistent. Extrahiere aus folgendem Vorlesungstext eine strukturierte Liste "
            "von konkreten Themenbegriffen für ein Informatikstudium.\n\n"
            f"{folien_text}\n\n"
            "Gib nur die Themen als JSON-Liste zurück."
        )
    )
    return response.text

def evaluate_video_quality(video_url, thema):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=(
            f"Bewerte die Qualität des Videos {video_url} hinsichtlich folgender Thematik: '{thema}'. "
            "Beurteile insbesondere die Tiefe, akademische Korrektheit und Verständlichkeit. "
            "Ist es für ein Informatik-Studium an einer Universität geeignet? Antworte differenziert."
        )
    )
    return response.text


# Testcode zum Extrahieren und Anzeigen der Themen aus PDFs im Ordner "pdfs"
if __name__ == "__main__":
    import json

    print("🌐 Starte Authentifizierung ...")
    youtube = get_authenticated_service()
    input("✅ Authentifizierung abgeschlossen. Drücke Enter zum Fortfahren ...\n")

    folder_path = "pdfs"  # Passe diesen Pfad bei Bedarf an
    themenliste = extract_themes_from_folder(folder_path)

    alle_themen = set()
    for t in themenliste:
        try:
            parsed = json.loads(t)
            alle_themen.update(parsed)
        except json.JSONDecodeError:
            print("Fehler beim Parsen eines Chunks:")
            print(t)
            continue

    print(f"\n📦 Insgesamt {len(alle_themen)} eindeutige Themen erkannt.")
    print("🧠 Beginne YouTube-Recherche ...")

    print("\n📚 Extrahierte Themen:")
    sortierte_themen = list(themenliste)  # Reihenfolge beibehalten
    for thema in sortierte_themen:
        print("-", thema)

    # Optional: automatische Video-Suche starten
    video_mapping = find_and_evaluate_videos_for_themes(sortierte_themen)
    add_all_videos_to_playlist(youtube, video_mapping)
