import csv
from datetime import datetime
from html import escape
import json
from pathlib import Path
from .engine import TITLES, WEIGHTS, risk_score
from .product import review_stats

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
                   "review_priority": risk_score(events), "weights": WEIGHTS, "review_summary": review_stats(events)}
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
    e = lambda value: escape(str(value), quote=True)
    thresholds = json.loads(session["settings"])
    summary = review_stats(events)
    done = summary["confirmed"] + summary["dismissed"]
    duration = max(1, session["duration"])
    rows, markers = [], []
    colors = {"phone": "#e67d55", "multiple": "#b78bda", "absence": "#dea94a", "head": "#5aa4cc", "window": "#6890ef"}
    for event in events:
        end = event["end"] if event["end"] is not None else session["duration"]
        length = "Нажатие" if event["kind"] in {"alt_tab", "copy", "paste", "screenshot"} else f"{max(0, end-event['start']):.1f} с"
        verdict = event["review"]
        rows.append(f"<tr><td class='time'>{clock(event['start'])}</td><td><strong>{e(TITLES.get(event['kind'], event['kind']))}</strong><small>{e(event['detail'])}</small></td><td>{length}</td><td><span class='pill {verdict}'>{e(REVIEWS[verdict])}</span></td></tr>")
        x = min(99.4, max(0, 100 * event["start"] / duration))
        width = min(100 - x, max(.6, 100 * max(0, end - event["start"]) / duration))
        markers.append(f"<span class='mark' style='left:{x:.3f}%;width:{width:.3f}%;background:{colors.get(event['kind'], '#8595c4')}' title='{e(TITLES.get(event['kind'], event['kind']))} · {clock(event['start'])}'></span>")
    demo = '<div class="demo">ДЕМОРЕЖИМ · Синтетические события, не реальный экзамен</div>' if session["mode"] == "demo" else ""
    weights = "; ".join(f"{e(TITLES[k])}: {v}" for k, v in WEIGHTS.items())
    progress = round(100 * done / len(events)) if events else 0
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QORGAU AI — отчёт #{session['id']}</title><style>
:root{{--ink:#202d45;--muted:#7c8aa4;--blue:#3865f1;--line:#e6ebf4}}
*{{box-sizing:border-box}}body{{margin:0;background:#f2f5fa;color:var(--ink);font:14px/1.6 'Segoe UI',Arial,sans-serif;padding:40px 20px}}main{{max-width:1080px;margin:auto;background:white;border-radius:24px;overflow:hidden;box-shadow:0 12px 50px #1829470b}}
header{{background:linear-gradient(120deg,#182848,#294aab);color:white;padding:36px 40px;display:flex;justify-content:space-between;align-items:flex-start;gap:20px}}.brand{{font-size:12px;font-weight:800;letter-spacing:3px;color:#abc5ff}}h1{{font-size:35px;letter-spacing:-1px;line-height:1.25;margin:14px 0 10px}}header p{{margin:0;color:#c1d1f4}}.report-id{{border:1px solid #6682b4;border-radius:12px;padding:8px 14px;color:#cbdcff;white-space:nowrap;font-size:12px}}.body{{padding:30px 40px 40px}}.demo{{background:#fff3df;color:#926026;border-radius:10px;padding:12px 16px;margin-bottom:20px;font-weight:600}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}.stat{{padding:18px;background:#f7f9fd;border:1px solid var(--line);border-radius:14px}}.stat span,.eyebrow{{color:var(--muted);font-size:10px;font-weight:700;letter-spacing:1.4px}}.stat b{{display:block;font-size:26px;color:#263d72;margin:6px 0}}.stat small{{color:var(--muted)}}.metadata{{display:grid;grid-template-columns:1fr 1fr;gap:8px;color:var(--muted);font-size:12px;padding-bottom:12px}}.metadata strong{{color:var(--ink);font-weight:500}}h2{{font-size:19px;margin:28px 0 12px}}.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:20px}}.section-head p{{color:var(--muted);font-size:12px}}.track{{height:18px;background:#edf2fa;border-radius:8px;position:relative;margin:20px 0 6px;overflow:hidden}}.mark{{position:absolute;top:0;height:18px;border-radius:4px;min-width:5px}}.times{{display:flex;justify-content:space-between;color:var(--muted);font:11px Consolas,monospace}}.review{{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}}.review span{{padding:7px 12px;border-radius:8px;background:#f3f6fb;font-size:12px}}.progress{{height:5px;background:#edf2fa;border-radius:3px;margin:12px 0 24px}}.progress i{{display:block;height:5px;background:var(--blue);border-radius:3px;width:{progress}%}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:12px}}th{{text-align:left;font-size:10px;letter-spacing:1px;color:var(--muted);background:#f6f8fc;padding:12px}}td{{padding:14px 12px;border-bottom:1px solid var(--line);vertical-align:top}}td small{{display:block;font-size:11px;color:var(--muted);margin-top:5px;max-width:520px}}td.time{{font:12px Consolas,monospace;white-space:nowrap;color:#4563a0}}.pill{{display:inline-block;padding:5px 9px;border-radius:7px;font-size:10px;white-space:nowrap;background:#edf2fc;color:#657da9}}.pill.confirmed{{background:#fff0e7;color:#a46637}}.pill.dismissed{{background:#e9f7f0;color:#39826a}}.note{{white-space:pre-wrap;border:1px solid var(--line);border-left:3px solid var(--blue);border-radius:10px;padding:20px;background:#fafbfe}}.notice{{font-size:12px;color:var(--muted);margin-top:25px;padding:16px;background:#f6f8fc;border-radius:10px}}details{{margin-top:24px;border-top:1px solid var(--line);padding-top:16px;font-size:12px;color:var(--muted)}}summary{{cursor:pointer;color:#526785;font-weight:600}}footer{{display:flex;justify-content:space-between;align-items:center;margin-top:30px;color:var(--muted);font-size:11px;gap:16px}}button{{background:var(--blue);color:white;border:0;padding:12px 20px;border-radius:9px;font:600 13px 'Segoe UI',sans-serif;cursor:pointer}}
@media(max-width:700px){{body{{padding:10px}}header{{padding:24px;display:block}}h1{{font-size:27px}}.report-id{{display:inline-block;margin-top:18px}}.body{{padding:24px}}.stats{{grid-template-columns:1fr 1fr}}.metadata{{grid-template-columns:1fr}}.section-head{{display:block}}td,th{{padding:10px 7px}}footer{{align-items:flex-start;flex-direction:column}}}}
@media print{{@page{{margin:15mm}}body{{padding:0;background:white;font-size:11px}}main{{max-width:none;border-radius:0;box-shadow:none}}header{{padding:24px;background:#f0f3fa;color:#172d52}}header p,.brand,.report-id{{color:#36588d}}.body{{padding:15px 0}}button{{display:none}}tr,.stat,.note{{break-inside:avoid}}.table-wrap{{overflow:visible}}h2{{break-after:avoid}}td small{{color:#53627a}}}}
</style></head><body><main><header><div><div class="brand">QORGAU AI / EXAM INTELLIGENCE</div><h1>Отчёт о наблюдении</h1><p>{e(session['candidate'])} · {e(session['exam'])}</p></div><div class="report-id">СЕССИЯ #{session['id']:04d}</div></header>
<div class="body">{demo}<div class="metadata"><div>Начало: <strong>{e(local_time(session['started']))}</strong></div><div>Окончание: <strong>{e(local_time(session['ended']))}</strong></div><div>Статус: <strong>{e(STATUSES[session['status']])}</strong></div><div>Источник: <strong>{'Синтетический сценарий' if session['mode'] == 'demo' else 'Камера и Windows Security Monitor'}</strong></div></div>
<div class="stats"><div class="stat"><span>ДЛИТЕЛЬНОСТЬ</span><b>{clock(session['duration'])}</b><small>Время наблюдения</small></div><div class="stat"><span>СОБЫТИЯ</span><b>{len(events)}</b><small>За всю сессию</small></div><div class="stat"><span>ИНДЕКС ПРОВЕРКИ</span><b>{risk_score(events)} / 100</b><small>Приоритет просмотра</small></div><div class="stat"><span>ПРОВЕРЕНО</span><b>{done} / {len(events)}</b><small>Решения человека</small></div></div>
<div class="section-head"><h2>Хронология экзамена</h2><p>Короткая отметка — нажатие; полоса — эпизод</p></div><div class="track">{''.join(markers)}</div><div class="times"><span>00:00:00</span><span>{clock(session['duration'] / 2)}</span><span>{clock(session['duration'])}</span></div>
<div class="review"><span>Ожидают проверки: {summary['pending']}</span><span>Подтверждены: {summary['confirmed']}</span><span>Отклонены: {summary['dismissed']}</span></div><div class="progress"><i></i></div>
<div class="table-wrap"><table><thead><tr><th>ВРЕМЯ</th><th>СОБЫТИЕ / НАБЛЮДЕНИЕ</th><th>ДЛИТЕЛЬНОСТЬ</th><th>РЕШЕНИЕ</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="4">Событий не зарегистрировано</td></tr>'}</tbody></table></div>
<h2>Вывод проверяющего</h2><div class="note">{e(session['note'] or 'Вывод ещё не добавлен. Решение принимает проверяющий.')}</div>
<div class="notice">Индекс — сумма весов событий с ограничением 100, а не вероятность нарушения. Нажатие сочетания фиксирует попытку действия, содержимое буфера и экрана не читается. Alt+Tab и выход из окна могут зарегистрироваться одновременно. Подтверждение сигнала не является автоматической оценкой участника.</div>
<details><summary>Методика и настройки сессии</summary><p>Веса: {weights}. Отклонённые события сохраняются в исходном индексе для воспроизводимости.</p><p>YOLO11n / COCO · MediaPipe Face Landmarker · CPU.<br>Уверенность: человек {thresholds['confidence']:.2f}; телефон {thresholds.get('phone_confidence', thresholds['confidence']):.2f}; угол головы {thresholds['head_angle']:.0f}°.<br>Задержки: телефон {thresholds['phone_seconds']} с; люди {thresholds['multiple_seconds']} с; отсутствие {thresholds['absence_seconds']} с; голова {thresholds['head_seconds']} с; окно {thresholds['window_seconds']} с.<br>Кадры событий: {'включены' if thresholds['save_evidence'] else 'выключены'}. Полная видеозапись не ведётся.</p></details>
<footer><span>QORGAU AI · Данные обработаны локально · Решение за человеком</span><button onclick="window.print()">Печать / сохранить PDF</button></footer></div></main></body></html>"""
