"""Localized copy for the first-summary push, one entry per app locale (``app/lib/l10n``).

The title names the summary with the app's own word for its Summary tab. The fallback body is
only used for an untitled conversation; a titled one shows its title, already written in the
same output language.
"""

# language: (title, fallback body)
FIRST_SUMMARY_COPY = {
    'ar': ('ملخصك الأول جاهز', 'اضغط للعرض'),
    'be': ('Ваша першая зводка гатовая', 'Натысніце, каб праглядаць'),
    'bg': ('Първото ви резюме е готово', 'Докоснете за преглед'),
    'bn': ('আপনার প্রথম সারসংক্ষেপ প্রস্তুত', 'দেখতে ট্যাপ করুন'),
    'bs': ('Vaš prvi sažetak je spreman', 'Dodirnite da vidite'),
    'ca': ('El teu primer resum està a punt', 'Toca per veure'),
    'cs': ('Váš první souhrn je připraven', 'Klepněte pro zobrazení'),
    'da': ('Dit første resumé er klar', 'Tryk for at se'),
    'de': ('Erste Zusammenfassung ist fertig', 'Tippen zum Anzeigen'),
    'el': ('Η πρώτη περίληψη είναι έτοιμη', 'Πατήστε για προβολή'),
    'en': ('Your first summary is ready', 'Tap to view'),
    'es': ('Tu primer resumen está listo', 'Toca para ver'),
    'et': ('Teie esimene kokkuvõte on valmis', 'Puudutage vaatamiseks'),
    'fa': ('اولین خلاصه شما آماده است', 'برای مشاهده ضربه بزنید'),
    'fi': ('Ensimmäinen yhteenveto valmis', 'Napauta nähdäksesi'),
    'fr': ('Votre premier résumé est prêt', 'Appuyez pour voir'),
    'he': ('הסיכום הראשון שלך מוכן', 'הקש כדי להציג'),
    'hi': ('आपका पहला सारांश तैयार है', 'देखने के लिए टैप करें'),
    'hr': ('Vaš prvi sažetak je spreman', 'Dodirnite za pregled'),
    'hu': ('Elkészült az első összefoglalója', 'Koppintson a megtekintéshez'),
    'id': ('Ringkasan pertama Anda siap', 'Ketuk untuk melihat'),
    'it': ('Il tuo primo riepilogo è pronto', 'Tocca per visualizzare'),
    'ja': ('最初の要約ができました', 'タップして表示'),
    'kn': ('ಮೊದಲ ಸಾರಾಂಶ ಸಿದ್ಧವಾಗಿದೆ', 'ವೀಕ್ಷಿಸಲು ಟ್ಯಾಪ್ ಮಾಡಿ'),
    'ko': ('첫 요약이 준비되었습니다', '탭하여 보기'),
    'lt': ('Jūsų pirmoji santrauka paruošta', 'Bakstelėkite, kad pamatytumėte'),
    'lv': ('Pirmais kopsavilkums ir gatavs', 'Pieskarieties, lai skatītu'),
    'mk': ('Првото резиме е подготвено', 'Допри за преглед'),
    'mr': ('तुमचा पहिला सारांश तयार आहे', 'पाहण्यासाठी टॅप करा'),
    'ms': ('Ringkasan pertama anda sedia', 'Ketik untuk melihat'),
    'nl': ('Je eerste samenvatting is klaar', 'Tik om te bekijken'),
    'no': ('Ditt første sammendrag er klart', 'Trykk for å se'),
    'pl': ('Pierwsze podsumowanie gotowe', 'Dotknij, aby wyświetlić'),
    'pt': ('Seu primeiro resumo está pronto', 'Toque para ver'),
    'ro': ('Primul tău rezumat este gata', 'Atingeți pentru a vizualiza'),
    'ru': ('Ваше первое резюме готово', 'Нажмите для просмотра'),
    'sk': ('Vaše prvé zhrnutie je pripravené', 'Klepnite pre zobrazenie'),
    'sl': ('Vaš prvi povzetek je pripravljen', 'Tapni za prikaz'),
    'sr': ('Ваш први резиме је спреман', 'Притисни да видиш'),
    'sv': ('Din första sammanfattning är klar', 'Tryck för att visa'),
    'ta': ('உங்கள் முதல் சுருக்கம் தயார்', 'பார்க்க தட்டவும்'),
    'te': ('మొదటి సారాంశం సిద్ధంగా ఉంది', 'చూడటానికి నొక్కండి'),
    'th': ('สรุปแรกของคุณพร้อมแล้ว', 'แตะเพื่อดู'),
    'tl': ('Handa na ang iyong unang buod', 'I-tap upang tingnan'),
    'tr': ('İlk özetiniz hazır', 'Görüntülemek için dokunun'),
    'uk': ('Ваше перше резюме готове', 'Торкніться для перегляду'),
    'ur': ('آپ کا پہلا خلاصہ تیار ہے', 'دیکھنے کے لیے ٹیپ کریں'),
    'vi': ('Bản tóm tắt đầu tiên đã sẵn sàng', 'Nhấn để xem'),
    'zh': ('您的第一份摘要已生成', '点击查看'),
}

# Codes the app files under another locale.
_ALIASES = {'nb': 'no', 'nn': 'no', 'fil': 'tl', 'iw': 'he', 'in': 'id'}


def first_summary_copy(language: str) -> tuple[str, str]:
    """Title and untitled-fallback body for a normalized language code; English when unsupported."""
    code = (language or '').lower()
    base = code.split('-', 1)[0]
    for candidate in (code, base, _ALIASES.get(base, '')):
        if candidate in FIRST_SUMMARY_COPY:
            return FIRST_SUMMARY_COPY[candidate]
    return FIRST_SUMMARY_COPY['en']
