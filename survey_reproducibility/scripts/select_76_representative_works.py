from pathlib import Path
import json,re
R=Path(__file__).resolve().parent;r=R.parent
# Keys below all already occur in the corresponding body section. No new bibliography entries.
groups=[
('Evidence\\\\construction','sec:evidence','rrmapEv','705C8D','evidence',[
('Noise & distraction','Retrieval Noise and Distracting Evidence',[('Irrelevant context','irrelevantContext2023'),('RGB','rgb2023'),('Power of Noise','cuconasu2024powerofnoise'),('Robust RALMs','rrag037')]),
('Filtering & compression','Filtering, Reranking, and Compression',[('FILCO','rrag044'),('RECOMP','rrag226'),('Discern-and-Answer','rrag043'),('UDCG','rrag058')]),
('Budget & order','Context Order, Length, and Query Formulation',[('LDAR','rrag131'),('Lost in the Middle','liu2024lostmiddle'),('Lost in the Evidence','rrag143'),('Long-context RAG','rrag039')]),
('Query & pipeline','Context Order, Length, and Query Formulation',[('Query robustness','queryRobustness2025'),('RAG best practices','ragBestPractices2024'),('Denoising-first IR','rrag073')]),
('Provenance & time','Provenance and Temporal Relevance',[('RA-RAG','sourceReliabilityRAG2025'),('KILT','kilt2021'),('FreshLLMs','freshllms2024'),('RealTime QA','realtimeQA2023')])]),
('Evidence\\\\use','sec:model','rrmapMd','476F95','model',[
('Learning under noise','Learning to Use Evidence under Noise',[('RAFT','rrag115'),('RAAT','raat2024'),('Chain-of-Note','chainOfNote2023'),('Context-DPO','rrag042')]),
('Memory--context conflict','Parametric--Context Knowledge Conflicts',[('Tug-of-War','tugOfWar2024'),('FaithfulRAG','faithfulRAG2025'),('Astute RAG','astuteRAG2025'),('CoReCt','rrag008')]),
('Source conflicts','Conflicts between Retrieved Sources',[('ConflictBank','conflictBank2024'),('MAGIC','rrag029'),('Whose Facts Win?','rrag132'),("Who’s Who",'rrag110')]),
('Internal integration','Internal Mechanisms for Knowledge Integration',[('ParamMute','rrag024'),('Parenting','rrag214'),('Latent probing','rrag088'),('Dual-stream knowledge','rrag206')]),
('Grounding & evaluation','Grounded Generation and Attribution',[('ALCE','alce2023'),('RAGTruth','ragTruth2024'),('RAGAS','ragas2024'),('ARES','ares2024')])]),
('Adversarial\\\\setting','sec:adversarial','rrmapAt','A15E55','adversarial',[
('Poisoning & backdoors','Corpus Poisoning: From Retrieval to Answer Steering',[('Retrieval poisoning','poisoningRetrievalCorpora2023'),('PoisonedRAG','poisonedRAG2024'),('BadRAG','badRAG2024'),('TrojanRAG','trojanRAG2024')]),
('Attack generalisation','Attack Generalisation, Budgets, and Transfer',[('LIAR','rrag035'),('MIRAGE','rrag028'),('CorruptRAG','rrag057'),('Joint-GCG','rrag050')]),
('Injection & persistence','Indirect Prompt Injection and Data Leakage',[('AIP','aip2025'),('AgentPoison','rrag053'),('AdversarialCoT','rrag010'),('Spill the Beans','venue200SpillBeans')]),
('Detection & filtering','Defence Families and Their Assumptions',[('CleanBase','rrag009'),('ProGRank','rrag004'),('SeCon-RAG','rrag017'),('TrustRAG','rrag013')]),
('Isolation & traceback','Defence Families and Their Assumptions',[('SDAG','rrag011'),('RobustRAG','certifiedRAG2024'),('Traceback','rrag128')])]),
('Adaptive\\\\control','sec:system','rrmapCt','667F56','system',[
('Retrieve & correct','Adaptive and Corrective Retrieval',[('Self-RAG','selfRAG2023'),('CRAG','crag2024'),('CtrlA','ctrla2025'),('When to Retrieve','whenToRetrieve2024')]),
('Sufficiency & answerability','Evidence Sufficiency and Answerability',[('Sufficient Context','sufficientContext2024'),('MTRAG-UN','rrag141'),('CRUMQs','rrag193'),('Unanswerability eval.','rrag111')]),
('Uncertainty & calibration','Uncertainty, Calibration, and Selective Answering',[('CalibRAG','calibRAG2025'),('UncertaintyRAG','uncertaintyRAG2024'),('URAG','rrag001'),('Noise-aware calib.','rrag007')]),
('Select, trust or defer','Joint Source Selection and Selective Verification',[('SABER','rrag002'),('BRIDGE','rrag092'),('SURE-RAG','rrag093')]),
('Verification & interaction','Verification, Interaction, and Cost',[('MAIN-RAG','mainRAG2025'),('MADAM-RAG','madamRAG2025'),('DRAG','drag2025')])])]
bbl=(r/'checks/v10_modified/source/main_survey.bbl').read_text();bib={}
for part in bbl.split('\\bibitem')[1:]:
 m=re.match(r'\[(.*?)\]\{([^}]+)\}',part,re.S)
 if m:bib[m.group(2)]={'bibitem_label':re.sub(r'\s+',' ',m.group(1)),'entry':part[m.end():].strip()}
result=[];allkeys=[]
for family,label,col,hexcolor,section,strands in groups:
 body=(r/'overleaf/survey_body_extracted'/f'{section}.tex').read_text();sectionkeys=set(k for m in re.finditer(r'\\cite\w*\*?(?:\[[^\]]*\])*\{([^}]+)\}',body) for k in m.group(1).split(','));rows=[]
 for j,(title,subsec,works) in enumerate(strands):
  row={'title':title,'subsection':subsec,'anchor':f'sec:map11-{section}-{j}','works':[]}
  for alias,key in works:
   assert key in sectionkeys and key in bib,(section,key);allkeys.append(key);row['works'].append({'alias':alias,'key':key,'bibliography':bib[key]})
  rows.append(row)
 result.append({'family':family,'label':label,'color':col,'hex':hexcolor,'section':section,'rows':rows})
assert len(allkeys)==len(set(allkeys))==76
old=json.loads((r/'figures_v10/checks/native_map_manifest.json').read_text())['bibliography_keys'];assert set(old)<=set(allkeys)
(R/'checks/expanded_data.json').write_text(json.dumps({'groups':result,'distinct_papers':len(allkeys),'strands':20,'old_papers':21,'retained_old_keys':old,'newly_added_keys':sorted(set(allkeys)-set(old)),'all_already_cited_in_respective_body_section':True,'note':'Short descriptive labels are used where a paper has no established method acronym; study/resource papers are not claimed to be interventions.'},ensure_ascii=False,indent=2)+'\n')
print('PAPERS=76; ADDED=55; RETAINED=21; STRANDS=20; ALREADY_DISCUSSSED_IN_CORRESPONDING_SECTION=PASS')
