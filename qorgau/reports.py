import csv
from datetime import datetime
from html import escape
import json
from pathlib import Path
from .engine import TITLES, WEIGHTS, risk_score

REVIEWS = {"pending": "Ожидает проверки", "confirmed": "Подтверждено", "dismissed": "Отклонено"}
STATUSES = {"running": "Идёт", "completed": "Завершена", "interrupted": "Прервана"}


def clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def local_time(value):
    return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M:%S %z") if value else "—"


def export_report(db, session_id: int, destination: Path):
    session, events = db.session(session_id), db.events(session_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()
    if suffix == ".json":
        session["settings"] = json.loads(session["settings"])
        payload = {"schema_version": 1, "session": session, "events": events,
                   "review_priority": risk_score(events), "weights": WEIGHTS}
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    elif suffix == ".csv":
        with destination.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["session_id", "event_id", "event", "start_seconds", "end_seconds", "duration_seconds", "detail", "review"])
            for event in events:
                detail = event["detail"]
                # Avoid spreadsheet formula interpretation of externally supplied strings.
                if detail.startswith(("=", "+", "-", "@")):
                    detail = "'" + detail
                end = event["end"] if event["end"] is not None else session["duration"]
                writer.writerow([session_id, event["id"], TITLES.get(event["kind"], event["kind"]), round(event["start"], 2), round(end, 2), round(max(0, end-event["start"]), 2), detail, REVIEWS[event["review"]]])
    elif suffix == ".html":
        destination.write_text(report_html(session, events), encoding="utf-8")
    else:
        raise ValueError("Поддерживаются HTML, CSV и JSON")
    return destination


def report_html(session, events):
    e = lambda v: escape(str(v), quote=True)
    rows = []
    for event in events:
        end = event["end"] if event["end"] is not None else session["duration"]
        rows.append(f"<tr><td>{clock(event['start'])}</td><td>{e(TITLES.get(event['kind'], event['kind']))}</td><td>{max(0,end-event['start']):.1f} с</td><td>{e(event['detail'])}</td><td>{e(REVIEWS[event['review']])}</td></tr>")
    demo = '<div class="demo">ДЕМОРЕЖИМ · Синтетические события, не реальный экзамен</div>' if session["mode"] == "demo" else ""
    thresholds = json.loads(session["settings"])
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QORGAU AI — отчёт #{session['id']}</title><style>
body{{font:15px/1.6 'Segoe UI',Arial,sans-serif;color:#203439;background:#edf2f1;margin:0;padding:40px}}
main{{max-width:1040px;margin:auto;background:white;padding:40px;border-radius:20px}}h1{{font-size:32px;margin:0}}.brand{{letter-spacing:3px;color:#13806c;font-weight:bold}}.muted{{color:#617477}}.demo{{padding:12px;background:#fff0ce;border-radius:8px;margin:20px 0}}.stats{{display:flex;gap:32px;margin:28px 0;flex-wrap:wrap}}.stats b{{display:block;font-size:26px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dce6e3}}th{{background:#f1f6f4}}.note{{white-space:pre-wrap;background:#f1f6f4;padding:16px}}button{{background:#167e69;color:white;border:0;padding:12px 20px;border-radius:8px;cursor:pointer}}@media print{{body{{padding:0;background:white}}main{{padding:0}}button{{display:none}}tr{{break-inside:avoid}}}}@media(max-width:600px){{body{{padding:12px}}main{{padding:20px}}table{{font-size:11px}}td,th{{padding:6px}}}}</style>
<main><div class="brand">QORGAU AI / EXAM REPORT</div><h1>Отчёт экзамена #{session['id']}</h1>{demo}
<p><b>{e(session['candidate'])}</b> · {e(session['exam'])}</p><p class="muted">Начало: {e(local_time(session['started']))}<br>Окончание: {e(local_time(session['ended']))}<br>Статус: {e(STATUSES[session['status']])}</p>
<div class="stats"><div><b>{clock(session['duration'])}</b>Длительность</div><div><b>{len(events)}</b>Событий</div><div><b>{risk_score(events)}/100</b>Приоритет проверки</div></div>
<p>Индекс — сумма весов эпизодов с ограничением 100, а не вероятность нарушения. Телефон: 20; несколько людей: 15; отсутствие: 10; поворот головы: 5; окно: 10. Технические ошибки: 0. Отклонённые события сохраняются в исходном индексе для воспроизводимости. Решение принимает проверяющий.</p>
<table><thead><tr><th>Время</th><th>Событие</th><th>Длительность</th><th>Наблюдение</th><th>Проверка</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="5">Событий не зарегистрировано</td></tr>'}</tbody></table>
<h3>Комментарий проверяющего</h3><div class="note">{e(session['note'] or 'Не добавлен')}</div>
<h3>Настройки сессии</h3><p class="muted">YOLO11n / COCO · MediaPipe Face Landmarker · CPU<br>Уверенность: человек {thresholds['confidence']:.2f}; телефон {thresholds.get('phone_confidence', thresholds['confidence']):.2f}; поворот головы: {thresholds['head_angle']:.0f}°.<br>Задержки: телефон {thresholds['phone_seconds']} с; люди {thresholds['multiple_seconds']} с; отсутствие {thresholds['absence_seconds']} с; голова {thresholds['head_seconds']} с; окно {thresholds['window_seconds']} с.<br>Сохранение кадров: {'включено' if thresholds['save_evidence'] else 'выключено'}. Полная видеозапись не ведётся.</p>
<button onclick="window.print()">Печать / сохранить PDF</button></main></html>"""
