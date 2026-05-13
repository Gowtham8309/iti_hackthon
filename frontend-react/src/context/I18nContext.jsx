import { createContext, useContext, useState } from 'react'

const LANGUAGE_KEY = 'iti_ui_language'

const dictionaries = {
  common: {
    logout: { en: 'Logout', te: 'లాగ్ అవుట్' },
    dashboard: { en: 'Dashboard', te: 'డాష్‌బోర్డ్' },
    master_data: { en: 'Master Data', te: 'మాస్టర్ డేటా' },
    attendance_history: { en: 'Attendance History', te: 'హాజరు చరిత్ర' },
    review_anomalies: { en: 'Review Anomalies', te: 'అసాధారణాలను సమీక్షించండి' },
    face_enrollment: { en: 'Face Enrollment', te: 'ముఖం నమోదు' },
    student_checkin: { en: 'Attendance Console', te: 'హాజరు కన్సోల్' },
    classroom_monitor: { en: 'Classroom Monitor', te: 'తరగతి మానిటర్' },
    refresh: { en: 'Refresh', te: 'రిఫ్రెష్' },
  },
  index: {
    hero_title: { en: 'AI-Powered ITI Monitoring Intelligence', te: 'ఏఐ ఆధారిత ఐటీఐ మానిటరింగ్ ఇంటెలిజెన్స్' },
    hero_text: { en: 'Face-authenticated attendance, geo-fenced proof of presence, classroom-quality monitoring, anomaly intelligence, and district-ready audit trails.', te: 'ముఖ ధృవీకరణ హాజరు, జియోఫెన్స్ హాజరు సాక్ష్యం, తరగతి నాణ్యత పర్యవేక్షణ, అసాధారణ గుర్తింపు మరియు జిల్లా స్థాయి ఆడిట్ ట్రెయిల్స్.' },
    command_center: { en: 'Command Center', te: 'కమాండ్ సెంటర్' },
    live_analytics: { en: 'Live Analytics', te: 'లైవ్ అనలిటిక్స్' },
    readiness_title: { en: 'Operational Readiness', te: 'ఆపరేషనల్ రెడీనెస్' },
    quick_actions: { en: 'Quick Actions', te: 'త్వరిత చర్యలు' },
  },
  checkin: {
    page_title: { en: 'Faculty And Attendance Intelligence', te: 'ఫ్యాకల్టీ మరియు హాజరు ఇంటెలిజెన్స్' },
    page_subtitle: { en: 'Captures selfie evidence, verifies face identity, validates GPS geofence, checks duty timing, and generates an explainable trust decision.', te: 'సెల్ఫీ ఆధారాన్ని సేకరిస్తుంది, ముఖాన్ని ధృవీకరిస్తుంది, GPS జియోఫెన్స్‌ను ధృవీకరిస్తుంది.' },
    console_title: { en: 'Check-In Console', te: 'హాజరు కన్సోల్' },
    details_title: { en: 'Check-In Details', te: 'హాజరు వివరాలు' },
    camera_title: { en: 'Camera Capture', te: 'కెమెరా క్యాప్చర్' },
    decision_title: { en: 'AI Attendance Decision', te: 'ఏఐ హాజరు నిర్ణయం' },
  },
  anomalies: {
    header_title: { en: 'Supervisor Anomaly Review Desk', te: 'సూపర్‌వైజర్ అసాధారణ సమీక్ష కేంద్రం' },
    header_subtitle: { en: 'Review suspicious attendance events, inspect risk scores, and approve, reject, or escalate cases.', te: 'అనుమానాస్పద హాజరు ఘటనలను సమీక్షించండి, రిస్క్ స్కోర్లు తనిఖీ చేయండి.' },
    snapshot_title: { en: 'Review Snapshot', te: 'సమీక్ష స్నాప్‌షాట్' },
    queue_title: { en: 'Anomaly Queue', te: 'అసాధారణ క్యూ' },
    kpi_total_loaded: { en: 'Total Loaded', te: 'మొత్తం లోడ్ అయింది' },
    kpi_pending: { en: 'Pending Review', te: 'సమీక్ష పెండింగ్' },
    kpi_high_risk: { en: 'Critical / High', te: 'క్రిటికల్ / హై' },
    kpi_reviewed: { en: 'Reviewed', te: 'సమీక్షించబడింది' },
    btn_load: { en: 'Load Anomalies', te: 'అసాధారణాలను లోడ్ చేయండి' },
    btn_reset: { en: 'Reset', te: 'రీసెట్' },
  },
  attendance_events: {
    header_title: { en: 'Attendance Audit Trail', te: 'హాజరు ఆడిట్ ట్రెయిల్' },
    header_subtitle: { en: 'Every check-in with identity verification, GPS validation, and authenticated selfie proof.', te: 'గుర్తింపు ధృవీకరణ, GPS ధ్రువీకరణ మరియు ధృవీకృత సెల్ఫీ ఆధారంతో ప్రతి హాజరు రికార్డు.' },
    snapshot_title: { en: 'Audit Snapshot', te: 'ఆడిట్ స్నాప్‌షాట్' },
    kpi_events_loaded: { en: 'Events Loaded', te: 'ఘటనలు లోడ్ అయ్యాయి' },
    kpi_present: { en: 'Present Events', te: 'హాజరు ఘటనలు' },
    kpi_review: { en: 'Review Events', te: 'సమీక్ష ఘటనలు' },
    kpi_selfies: { en: 'Selfies Saved', te: 'సెల్ఫీలు సేవ్ అయ్యాయి' },
    btn_load: { en: 'Load Events', te: 'ఘటనలను లోడ్ చేయండి' },
    btn_reset: { en: 'Reset', te: 'రీసెట్' },
  },
  classroom: {
    header_title: { en: 'Classroom Quality Monitor', te: 'తరగతి నాణ్యత మానిటర్' },
    header_subtitle: { en: 'Record faculty session observations, score discipline and teaching quality, and surface automated anomaly signals.', te: 'ఫ్యాకల్టీ సెషన్ పరిశీలనలు నమోదు చేయండి, క్రమశిక్షణ మరియు బోధన నాణ్యతను స్కోర్ చేయండి.' },
    snapshot_title: { en: 'Quality Snapshot', te: 'నాణ్యత స్నాప్‌షాట్' },
    kpi_observed: { en: 'Observed Today', te: 'ఈరోజు పరిశీలించబడింది' },
    kpi_attention: { en: 'Needs Attention', te: 'శ్రద్ధ అవసరం' },
    kpi_discipline: { en: 'Avg Discipline', te: 'సగటు క్రమశిక్షణ' },
    kpi_teaching: { en: 'Avg Teaching Quality', te: 'సగటు బోధన నాణ్యత' },
    kpi_engagement: { en: 'Avg Engagement', te: 'సగటు నిమగ్నత' },
    kpi_composite: { en: 'Avg Composite', te: 'సగటు సమ్మిళిత స్కోర్' },
    form_title: { en: 'Record Classroom Observation', te: 'తరగతి పరిశీలన నమోదు చేయండి' },
    btn_submit: { en: 'Submit Observation', te: 'పరిశీలన సమర్పించండి' },
    btn_reset: { en: 'Reset Form', te: 'ఫారమ్ రీసెట్' },
    btn_load: { en: 'Load Observations', te: 'పరిశీలనలు లోడ్ చేయండి' },
    history_title: { en: 'Observation History', te: 'పరిశీలన చరిత్ర' },
  },
  master_data: {
    page_title: { en: 'Master Data Control Center', te: 'మాస్టర్ డేటా కంట్రోల్ సెంటర్' },
    page_subtitle: { en: 'Configure trainees, industry partners, and training rosters.', te: 'శిక్షణార్థులు, పరిశ్రమ భాగస్వాములు, రోస్టర్లు సెటప్ చేయండి.' },
    students_tab: { en: 'Profiles', te: 'ప్రొఫైల్లు' },
    industries_tab: { en: 'Industries', te: 'పరిశ్రమలు' },
    rosters_tab: { en: 'Rosters', te: 'రోస్టర్లు' },
    pilot_import_tab: { en: 'Pilot Import', te: 'పైలట్ ఇంపోర్ట్' },
    day_states_tab: { en: 'Day States', te: 'రోజువారీ స్థితులు' },
    evaluation_tab: { en: 'Evaluation', te: 'మూల్యాంకనం' },
    payroll_tab: { en: 'Payroll', te: 'వేతన జాబితా' },
    payroll_title: { en: 'Payroll Summary', te: 'వేతన సారాంశం' },
    payroll_subtitle: { en: 'Attendance-based working day counts per trainee for HR/payroll sync.', te: 'HR/వేతన సమకాలీకరణ కోసం శిక్షణార్థి వారీగా హాజరు ఆధారిత పని రోజుల లెక్క.' },
  },
}

const I18nContext = createContext(null)

export function I18nProvider({ children }) {
  const [language, setLanguage] = useState(() => localStorage.getItem(LANGUAGE_KEY) || 'en')

  function changeLanguage(lang) {
    localStorage.setItem(LANGUAGE_KEY, lang)
    setLanguage(lang)
  }

  function t(key, pageKey = 'common') {
    const pageDict = dictionaries[pageKey] || {}
    const entry = pageDict[key] || dictionaries.common[key]
    if (!entry) return key
    return entry[language] || entry.en || key
  }

  return (
    <I18nContext.Provider value={{ language, changeLanguage, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  return useContext(I18nContext)
}
