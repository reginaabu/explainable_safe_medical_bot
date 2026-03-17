"""
scripts/generate_archehr_sample.py
------------------------------------
Generate a synthetic ArchEHR-QA dataset in the exact PhysioNet XML format,
using real patient narratives from the public GitHub dev set combined with
synthetic (but realistic) note excerpt sentences.

Use this to test the pipeline locally without PhysioNet credentials.

Usage
-----
    python scripts/generate_archehr_sample.py
    python scripts/generate_archehr_sample.py --n 10 --out data/archehr_sample

Evaluate:
    python run_pipeline.py track3-eval \\
        --dataset archehr_qa \\
        --csv-path data/archehr_sample \\
        --n 10 --seed 42

Once you have PhysioNet access, simply point --csv-path to the real
archehr-qa.xml file (or its directory) and everything else works identically.
"""
from __future__ import annotations

import argparse
import json
import textwrap
import xml.dom.minidom
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Synthetic cases — patient narratives taken from the public GitHub dev set
# (https://github.com/soni-sarvesh/archehr-qa) plus synthetic note excerpts.
# ---------------------------------------------------------------------------
CASES = [
    {
        "id": "1",
        "document_source": "mimic-iii",
        "patient_narrative": (
            "I had severe abdomen pain and was hospitalised for 15 days in ICU, "
            "diagnosed with CBD sludge thereafter on udiliv. Doctor advised for ERCP. "
            "My question is if the sludge was there does not the medication help in "
            "flushing it out? Whether ERCP was the only cure?"
        ),
        "patient_question": [
            (0, 141, "My question is if the sludge was there does not the medication help "
                     "in flushing it out? Whether ERCP was the only cure?"),
        ],
        "clinician_question": "Why was ERCP recommended over continuing a medication-based treatment?",
        "sentences": [
            (0, 0, "Patient is a 52-year-old male presenting with right upper quadrant pain "
                   "and jaundice for 3 days."),
            (1, 0, "Abdominal ultrasound demonstrated common bile duct dilation to 12 mm "
                   "with echogenic material (sludge/calculi) in the CBD."),
            (2, 1, "Ursodiol (Udiliv) was initiated but repeat imaging after 10 days showed "
                   "persistent obstruction with rising bilirubin (total 8.4 mg/dL)."),
            (3, 1, "Given failed medical management and ongoing biliary obstruction, "
                   "gastroenterology recommended ERCP for stone/sludge extraction."),
            (4, 2, "Procedure was uncomplicated; CBD was cleared of sludge and a temporary "
                   "biliary stent was placed."),
            (5, 2, "Bilirubin normalised to 1.2 mg/dL at 48-hour post-ERCP check."),
            (6, 3, "Patient's breakfast preferences were noted in the chart."),
        ],
        "relevant_ids": {"1", "2", "3", "4", "5"},
    },
    {
        "id": "2",
        "document_source": "mimic-iii",
        "patient_narrative": (
            "I just wrote about my dad given multiple shots of lasix after he was already "
            "so swelled his shin looked like it would burst open. Why would they give him so "
            "much. He was on oxygen and they took him off of the higher flow rate."
        ),
        "patient_question": [
            (0, 22, "dad given multiple shots of lasix after he was already so swelled his "
                    "shin looked like it would burst open. Why would they give him so much."),
        ],
        "clinician_question": "Why was he given multiple doses of furosemide and why was his oxygen flow rate reduced?",
        "sentences": [
            (0, 0, "Patient is a 71-year-old male with a history of ischemic cardiomyopathy "
                   "(EF 25%) and chronic kidney disease stage 3 admitted for acute decompensated "
                   "heart failure."),
            (1, 0, "On admission, examination revealed 3+ pitting oedema to the mid-thighs "
                   "bilaterally and tense ascites; estimated 15 kg volume overload."),
            (2, 1, "Intravenous furosemide 80 mg was administered; repeat assessment at 4 hours "
                   "showed inadequate urine output (<500 mL), prompting a second dose of 120 mg IV."),
            (3, 1, "Aggressive diuresis was required to relieve pulmonary congestion contributing "
                   "to hypoxia; SpO2 improved from 88% to 96% after second diuretic dose."),
            (4, 2, "Supplemental oxygen was weaned from 4 L/min to 2 L/min as pulmonary oedema "
                   "resolved on chest X-ray over 48 hours."),
            (5, 2, "Renal function remained stable with creatinine 1.9 mg/dL (baseline 1.7)."),
            (6, 3, "Nurse documented patient preference for evening bath."),
        ],
        "relevant_ids": {"0", "1", "2", "3", "4"},
    },
    {
        "id": "3",
        "document_source": "mimic-iii",
        "patient_narrative": (
            "my son fell and lost consciousness for a couple mins. we rushed him to hospital "
            "took a CT scan there was bleeding in the brain we got him admitted in icu and he "
            "was under observ. they were giving him pain killers and injected to prevent him "
            "from vomiting yesterday i got him back home but he is continuously irritated and "
            "has headache when awake what do i do"
        ),
        "patient_question": [
            (0, 289, "he is continuously irritated and has headache when awake what do i do"),
        ],
        "clinician_question": "What is the expected course of recovery for a child with traumatic intracranial haemorrhage?",
        "sentences": [
            (0, 0, "Patient is a 9-year-old male admitted following a fall from approximately "
                   "2 metres with loss of consciousness lasting approximately 2 minutes."),
            (1, 0, "Non-contrast CT head revealed a small subdural haematoma (5 mm maximum "
                   "thickness) in the right temporal region without midline shift."),
            (2, 1, "Neurosurgery was consulted; non-operative management with observation was "
                   "recommended given haematoma size and clinical stability."),
            (3, 1, "Post-concussive symptoms including headache and irritability are common "
                   "and expected following mild-moderate traumatic brain injury; they typically "
                   "resolve within 4–8 weeks."),
            (4, 2, "Patient was discharged with instructions to avoid contact sports and "
                   "screen time for 2 weeks and to return if headaches worsen, vomiting recurs, "
                   "or any focal neurological deficits develop."),
            (5, 2, "Follow-up CT and neurology appointment scheduled in 4 weeks."),
            (6, 3, "Patient's school attendance record was requested."),
        ],
        "relevant_ids": {"0", "1", "2", "3", "4", "5"},
    },
    {
        "id": "4",
        "document_source": "mimic-iii",
        "patient_narrative": (
            "I am 48 years old. On February 20, I passed out, was taken to the hospital, "
            "and had two other episodes. I have chronic kidney disease with creatinine around 1.5. "
            "I had anaemia and haemoglobin was 10.3. I was in ICU 8 days and discharged in stable "
            "condition. My doctor performed a cardiac catheterisation. I had no increase in cardiac "
            "enzymes and an ECHO in the hospital showed 25% LVEF. Was this invasive, risky "
            "procedure necessary."
        ),
        "patient_question": [
            (0, 254, "My doctor performed a cardiac catheterisation."),
            (1, 381, "Was this invasive, risky procedure necessary."),
        ],
        "clinician_question": "Why was cardiac catheterisation recommended to the patient?",
        "sentences": [
            (0, 0, "Patient is a 48-year-old male presenting with three syncopal episodes; "
                   "ECG on arrival showed sinus bradycardia and ST-segment depression in V4–V6."),
            (1, 0, "Transthoracic echocardiogram (TTE) demonstrated severely reduced LVEF of "
                   "25% with anterior wall hypokinesis, raising concern for ischaemic aetiology."),
            (2, 1, "Troponin I was 0.04 ng/mL (borderline); creatinine 1.5 mg/dL and "
                   "haemoglobin 10.3 g/dL noted."),
            (3, 1, "Given new-onset severe LV dysfunction and syncopal presentation, coronary "
                   "angiography was performed to exclude obstructive coronary artery disease as "
                   "a treatable cause."),
            (4, 2, "Coronary angiography revealed 85% stenosis of the proximal LAD; PCI with "
                   "drug-eluting stent was performed."),
            (5, 2, "Repeat LVEF at 4-week follow-up improved to 40%, confirming ischaemic "
                   "hibernating myocardium as the underlying aetiology."),
        ],
        "relevant_ids": {"0", "1", "3", "4", "5"},
    },
    {
        "id": "5",
        "document_source": "mimic-iii",
        "patient_narrative": (
            "I overdosed October 4th on trihexyphenidyl, thorazine, and cocaine. "
            "Ended up in icu with prolonged qt for 8 days. I have had chest pain in my "
            "left upper quadrant ever since. My doctor said it is related to muscle and bone. "
            "It is a dull to deep pain. Any ideas?"
        ),
        "patient_question": [
            (0, 0, "I overdosed October 4th on trihexyphenidyl, thorazine, and cocaine."),
            (1, 114, "I have had chest pain in my left upper quadrant ever since."),
            (2, 248, "Any ideas?"),
        ],
        "clinician_question": "Is the persistent chest pain connected to the overdose or another aetiology?",
        "sentences": [
            (0, 0, "Patient presented in a toxidrome following ingestion of trihexyphenidyl, "
                   "chlorpromazine (Thorazine), and cocaine with QTc 620 ms on admission ECG."),
            (1, 0, "ICU course was complicated by QT prolongation managed with IV magnesium, "
                   "temporary pacing, and withdrawal of offending agents."),
            (2, 1, "Rhabdomyolysis was documented (peak CK 14,200 U/L) consistent with cocaine "
                   "toxicity and prolonged muscle rigidity."),
            (3, 1, "Chest X-ray and CT chest at discharge showed resolving bilateral infiltrates "
                   "and no rib fractures; musculoskeletal chest pain is consistent with post-CPR "
                   "or prolonged rigidity."),
            (4, 2, "Persistent left-sided chest wall pain post-discharge is most likely "
                   "musculoskeletal (costochondritis or intercostal muscle strain) from the "
                   "prolonged toxic episode; cardiac workup was negative."),
            (5, 2, "Follow-up cardiology appointment was arranged for 6 weeks post-discharge."),
            (6, 3, "Patient's address was updated in the system."),
        ],
        "relevant_ids": {"0", "2", "3", "4"},
    },
    {
        "id": "11",
        "document_source": "mimic-iv",
        "patient_narrative": (
            "My mother had knee replacement surgery and two days later developed sudden "
            "shortness of breath. The doctors said she had a pulmonary embolism. She is "
            "now on blood thinners. How long will she need them and is she at risk again?"
        ),
        "patient_question": [
            (0, 95, "How long will she need them and is she at risk again?"),
        ],
        "clinician_question": "What is the recommended duration of anticoagulation following PE after orthopaedic surgery and the risk of recurrence?",
        "sentences": [
            (0, 0, "Patient is a 67-year-old female, post-operative day 2 following left total "
                   "knee arthroplasty, presenting with acute dyspnoea and desaturation to 88%."),
            (1, 0, "CT pulmonary angiography confirmed bilateral segmental pulmonary emboli."),
            (2, 1, "Anticoagulation with low molecular weight heparin was initiated and "
                   "transitioned to rivaroxaban 15 mg twice daily for 21 days then 20 mg daily."),
            (3, 1, "Provoked VTE following major orthopaedic surgery carries a low recurrence "
                   "risk; standard duration of anticoagulation is 3 months per ACCP guidelines."),
            (4, 2, "After completing 3 months of anticoagulation, annual recurrence risk falls "
                   "to approximately 3%, comparable to the general population."),
            (5, 2, "Compression stockings and early mobilisation are recommended to prevent "
                   "post-thrombotic syndrome."),
            (6, 3, "Social work referred for home nursing support post-discharge."),
        ],
        "relevant_ids": {"0", "1", "2", "3", "4"},
    },
    {
        "id": "12",
        "document_source": "mimic-iv",
        "patient_narrative": (
            "My father has Parkinson's disease and was admitted after a fall. "
            "The neurologist said he should have DBS. What is deep brain stimulation "
            "and how does it help Parkinson's?"
        ),
        "patient_question": [
            (0, 80, "What is deep brain stimulation and how does it help Parkinson's?"),
        ],
        "clinician_question": "What is the indication and mechanism of deep brain stimulation in advanced Parkinson's disease?",
        "sentences": [
            (0, 0, "Patient is a 72-year-old male with 12-year history of Parkinson's disease "
                   "presenting with recurrent falls secondary to severe on-off motor fluctuations "
                   "and dyskinesia despite optimised levodopa/carbidopa therapy."),
            (1, 0, "Motor UPDRS score 42/108 during 'off' state; 'off' periods comprise "
                   "approximately 6 hours per waking day."),
            (2, 1, "DBS eligibility workup initiated: neuropsychology testing, MRI brain, "
                   "and levodopa challenge (>30% UPDRS improvement confirmed)."),
            (3, 1, "Deep brain stimulation of the subthalamic nucleus (STN-DBS) delivers "
                   "high-frequency electrical pulses that modulate pathological basal ganglia "
                   "circuitry, reducing motor fluctuations and dyskinesia."),
            (4, 2, "Clinical trials show STN-DBS reduces 'off' time by approximately 50% and "
                   "levodopa equivalent daily dose by 30–50% in well-selected candidates."),
            (5, 2, "Neurosurgery has accepted referral; procedure scheduled for 8 weeks."),
        ],
        "relevant_ids": {"0", "1", "3", "4", "5"},
    },
    {
        "id": "13",
        "document_source": "mimic-iv",
        "patient_narrative": (
            "My wife was admitted with severe sepsis from a UTI. She was in ICU for 5 days. "
            "The doctor mentioned her lactate was very high. What does high lactate mean "
            "and why is it dangerous?"
        ),
        "patient_question": [
            (0, 90, "What does high lactate mean and why is it dangerous?"),
        ],
        "clinician_question": "What is the clinical significance of hyperlactataemia in septic shock and what does it indicate?",
        "sentences": [
            (0, 0, "Patient is a 58-year-old female admitted with fever, rigors, and confusion; "
                   "urine culture grew E. coli >100,000 CFU/mL."),
            (1, 0, "Initial lactate 6.8 mmol/L (normal <2.0) with MAP 58 mmHg despite 2L IV "
                   "fluid bolus, meeting Sepsis-3 criteria for septic shock."),
            (2, 1, "Elevated lactate in sepsis reflects tissue hypoperfusion and anaerobic "
                   "metabolism; lactate >4 mmol/L is associated with in-hospital mortality of "
                   "approximately 40%."),
            (3, 1, "Norepinephrine was commenced at 0.15 mcg/kg/min to maintain MAP >65 mmHg; "
                   "broad-spectrum antibiotics (piperacillin-tazobactam) started within 1 hour."),
            (4, 2, "Lactate clearance >10% at 2 hours is a treatment target; lactate fell "
                   "to 2.1 mmol/L by hour 6 following resuscitation."),
            (5, 2, "ICU course was 5 days; antibiotics de-escalated to trimethoprim based "
                   "on sensitivities."),
        ],
        "relevant_ids": {"1", "2", "3", "4"},
    },
    {
        "id": "14",
        "document_source": "mimic-iv",
        "patient_narrative": (
            "My son has sickle cell disease and was admitted for a pain crisis. "
            "They gave him IV fluids and morphine. Why can't his haemoglobin be fixed "
            "with a transfusion every time?"
        ),
        "patient_question": [
            (0, 112, "Why can't his haemoglobin be fixed with a transfusion every time?"),
        ],
        "clinician_question": "Why is routine transfusion not used to manage acute sickle cell pain crises?",
        "sentences": [
            (0, 0, "Patient is a 19-year-old male with HbSS sickle cell disease admitted "
                   "with acute vaso-occlusive crisis involving bilateral lower extremity and "
                   "lumbar pain, pain score 9/10."),
            (1, 0, "Haemoglobin on admission 7.2 g/dL (baseline 7.5–8.0); reticulocyte count "
                   "elevated at 12%, consistent with chronic haemolytic anaemia."),
            (2, 1, "Routine transfusion in vaso-occlusive crisis is not recommended as it "
                   "does not address the underlying pathophysiology (sickling due to HbSS "
                   "polymerisation under hypoxia) and raises viscosity risk."),
            (3, 1, "Repeated transfusions lead to iron overload, alloimmunisation (antibody "
                   "development in 30% of SCD patients), and hyperviscosity syndrome."),
            (4, 2, "Transfusion IS indicated for acute complications: stroke, acute chest "
                   "syndrome with SpO2 <95%, splenic sequestration, or haemoglobin <5 g/dL."),
            (5, 2, "Current management: IV hydration, IV morphine PCA, supplemental oxygen, "
                   "and hydroxyurea optimisation."),
        ],
        "relevant_ids": {"0", "1", "2", "3", "4"},
    },
    {
        "id": "15",
        "document_source": "mimic-iv",
        "patient_narrative": (
            "My grandmother was found to have atrial fibrillation. The doctor wants to "
            "cardiovert her. What does cardioversion mean and is it safe for an 81-year-old?"
        ),
        "patient_question": [
            (0, 70, "What does cardioversion mean and is it safe for an 81-year-old?"),
        ],
        "clinician_question": "What are the risks and benefits of electrical cardioversion for new-onset atrial fibrillation in an elderly patient?",
        "sentences": [
            (0, 0, "Patient is an 81-year-old female with hypertension and type 2 diabetes "
                   "presenting with palpitations and dyspnoea; ECG confirmed new-onset AF "
                   "with ventricular rate 130 bpm."),
            (1, 0, "Transoesophageal echocardiogram ruled out left atrial appendage thrombus; "
                   "CHA2DS2-VASc score 5, indicating high stroke risk."),
            (2, 1, "Electrical cardioversion (DC cardioversion) delivers a synchronised "
                   "electrical shock to restore sinus rhythm; success rates exceed 90% for "
                   "recent-onset AF."),
            (3, 1, "In elderly patients, cardioversion is generally safe under anaesthesia; "
                   "major risks include thromboembolic stroke (mitigated by pre-cardioversion "
                   "anticoagulation and TOE) and anaesthetic complications."),
            (4, 2, "Anticoagulation with apixaban was initiated; cardioversion scheduled "
                   "after minimum 3 weeks of therapeutic anticoagulation per guidelines."),
            (5, 2, "Long-term rate vs rhythm control strategy to be discussed at cardiology "
                   "follow-up given patient's age and functional status."),
        ],
        "relevant_ids": {"0", "1", "2", "3", "4"},
    },
]


def _build_xml(cases: list[dict]) -> str:
    """Build XML in the real ArchEHR-QA PhysioNet format."""
    root = ET.Element("annotations")

    for c in cases:
        case_el = ET.SubElement(root, "case", id=c["id"])

        # patient_narrative
        narr_el = ET.SubElement(case_el, "patient_narrative")
        narr_el.text = "\n" + textwrap.indent(c["patient_narrative"], "        ") + "\n    "

        # patient_question / phrase elements
        pq_el = ET.SubElement(case_el, "patient_question")
        for pid, start_char, phrase_text in c["patient_question"]:
            ph_el = ET.SubElement(pq_el, "phrase",
                                  id=str(pid), start_char_index=str(start_char))
            ph_el.text = "\n" + textwrap.indent(phrase_text, "            ") + "\n        "

        # clinician_question
        cq_el = ET.SubElement(case_el, "clinician_question")
        cq_el.text = "\n        " + c["clinician_question"] + "\n    "

        # note_excerpt (raw text placeholder)
        ne_el = ET.SubElement(case_el, "note_excerpt")
        ne_el.text = "\n        [Note excerpt from MIMIC discharge summary]\n    "

        # note_excerpt_sentences — SIBLING of note_excerpt (real format)
        sents_el = ET.SubElement(case_el, "note_excerpt_sentences")
        for sid, para_id, text in c["sentences"]:
            s_el = ET.SubElement(sents_el, "sentence",
                                 id=str(sid), paragraph_id=str(para_id),
                                 start_char_index="0")
            s_el.text = "\n            " + text + "\n        "

    raw = ET.tostring(root, encoding="unicode")
    return xml.dom.minidom.parseString(raw).toprettyxml(indent="    ")


def _build_key(cases: list[dict]) -> list[dict]:
    """Build the key JSON with sentence relevance labels."""
    entries = []
    for c in cases:
        answers = []
        for sid, _, _ in c["sentences"]:
            rel = "essential" if str(sid) in c["relevant_ids"] else "not-relevant"
            answers.append({"sentence_id": str(sid), "relevance": rel})
        entries.append({
            "case_id": c["id"],
            "answers": answers,
        })
    return entries


def _build_mapping(cases: list[dict]) -> list[dict]:
    """Build the mapping JSON linking cases to MIMIC document sources."""
    return [
        {"case_id": c["id"], "document_id": f"synthetic_{c['id']}",
         "document_source": c["document_source"]}
        for c in cases
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic ArchEHR-QA sample data for pipeline testing"
    )
    parser.add_argument("--n", type=int, default=len(CASES),
                        help=f"Number of cases to include (max {len(CASES)})")
    parser.add_argument("--out", default="data/archehr_sample",
                        help="Output directory (default: data/archehr_sample)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cases = CASES[: min(args.n, len(CASES))]
    xml_str = _build_xml(cases)
    key_data = _build_key(cases)
    mapping_data = _build_mapping(cases)

    xml_path = out / "archehr-qa.xml"
    key_path = out / "archehr-qa_key.json"
    mapping_path = out / "archehr-qa_mapping.json"

    xml_path.write_text(xml_str, encoding="utf-8")
    key_path.write_text(json.dumps(key_data, indent=2), encoding="utf-8")
    mapping_path.write_text(json.dumps(mapping_data, indent=2), encoding="utf-8")

    print(f"Written {len(cases)} cases to:")
    print(f"  {xml_path}")
    print(f"  {key_path}")
    print(f"  {mapping_path}")
    print()
    print("Run evaluation:")
    print(f"  python run_pipeline.py track3-eval "
          f"--dataset archehr_qa --csv-path {out} --n {len(cases)} --seed 42")
    print()
    print("Note: For the real dataset, sign the DUA at:")
    print("  https://physionet.org/content/archehr-qa-bionlp-task-2025/")
    print("  Then: python run_pipeline.py track3-eval "
          "--dataset archehr_qa --csv-path /path/to/real/archehr-qa.xml --n 20 --seed 42")


if __name__ == "__main__":
    main()
