from datetime import date

from app.intent import missing_slots, next_question, parse_intent

TODAY = date(2026, 10, 31)  # 24th of this month has passed
SENTENCES = {
    "en": "I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap.",
    "hinglish": "Main Paytm Marol office mein hoon. Mujhe kal lunch tak Connaught Place pahunchna hai, 24 ko wapas. Sasta chahiye.",
    "hi": "मैं पेटीएम मरोल ऑफ़िस में हूँ। मुझे कल दोपहर के खाने तक कनॉट प्लेस पहुँचना है, 24 को वापस। सस्ता चाहिए।",
}


def test_demo_sentence_all_languages():
    for lang, text in SENTENCES.items():
        p = parse_intent(text, today=TODAY)
        assert p.origin == "Paytm Marol office", lang
        assert p.destination == "Connaught Place", lang
        assert p.depart_date == "2026-11-01", lang  # tomorrow resolved from IST today
        assert p.return_date == "2026-11-03", lang  # 24th passed -> depart + 2 days
        assert p.arrive_by == "13:00", lang
        assert p.priority == "economical", lang
        assert missing_slots(p) == []


def test_return_date_used_when_valid():
    p = parse_intent(SENTENCES["en"], today=date(2026, 11, 10))
    assert p.depart_date == "2026-11-11"
    assert p.return_date == "2026-11-13"  # 24th is beyond the 9-day window -> depart + 2
    p = parse_intent("Marol to Connaught Place tomorrow, back on the 13th", today=date(2026, 11, 10))
    assert p.return_date == "2026-11-13"


def test_year_is_inferred_never_asked():
    p = parse_intent("I want to go from Borivali to Dubai on 5th November", today=TODAY)
    assert p.depart_date == "2026-11-05"
    p = parse_intent("Delhi trip on October 5", today=TODAY)  # already passed this year -> next year
    assert p.depart_date == "2027-10-05"
    p = parse_intent("Connaught Place on 5 Nov, back on 8 Nov", today=TODAY)
    assert (p.depart_date, p.return_date) == ("2026-11-05", "2026-11-08")
    p = parse_intent("मुझे 5 नवंबर को कनॉट प्लेस जाना है", today=TODAY)
    assert p.depart_date == "2026-11-05"


def test_one_question_at_a_time():
    p = parse_intent("I want to go to Connaught Place", today=TODAY)
    assert missing_slots(p) == ["origin", "depart_date"]
    q = next_question(missing_slots(p))
    assert q and "starting" in q[0]
    p = parse_intent("from Marol", today=TODAY, previous=p)
    assert missing_slots(p) == ["depart_date"]
