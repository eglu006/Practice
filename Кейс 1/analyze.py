import pandas as pd
import numpy as np

df = pd.read_csv('students.csv', header=0)

df['Timestamp'] = pd.to_datetime(df['Timestamp'])

print(f"Загружено строк: {len(df)}")
print(f"Уникальных процессов: {df['ProcessInstanceId'].nunique()}")

#1. task_created: UserId и Role должны быть пустыми
var1 = df[(df['EventType'] == 'task_created') & (df['UserId'].notna() | df['Role'].notna())]
print(f"1. Нарушений в task_created: {len(var1)}")

#2. automatic_completed: UserId пустой, Role = system
var2 = df[(df['EventType'] == 'automatic_completed') & (df['UserId'].notna() | (df['Role'] != 'system'))]
print(f"2. Нарушений в automatic_completed: {len(var2)}")

#3. task_completed: Result должен быть в [accept, return, reject]
valid_results = ['accept', 'return', 'reject', np.nan]
var3 = df[(df['EventType'] == 'task_completed') & (~df['Result'].isin(valid_results) & df['Result'].notna())]
print(f"3. Нарушений в Result для task_completed: {len(var3)}")



#А) Длительность задач (по TaskId)
task_created = df[df['EventType'] == 'task_created'][['TaskId', 'ProcessInstanceId', 'ActivityName', 'Timestamp']].rename(columns={'Timestamp': 'CreatedTime'})
task_completed = df[df['EventType'] == 'task_completed'][['TaskId', 'Timestamp', 'Result', 'Role']].rename(columns={'Timestamp': 'CompletedTime'})

#Объединяем только закрытые задачи (inner join)
task_merged = pd.merge(task_created, task_completed, on='TaskId', how='inner')
task_merged['DurationSeconds'] = (task_merged['CompletedTime'] - task_merged['CreatedTime']).dt.total_seconds()

#Б) Длительность процессов (по ProcessInstanceId)
process_started = df[df['EventType'] == 'process_started'][['ProcessInstanceId', 'Timestamp', 'RequestType', 'Amount']].rename(columns={'Timestamp': 'StartedTime'})
process_completed = df[df['EventType'] == 'process_completed'][['ProcessInstanceId', 'Timestamp', 'Result']].rename(columns={'Timestamp': 'CompletedTime'})

proc_merged = pd.merge(process_started, process_completed, on='ProcessInstanceId', how='inner')
proc_merged['DurationSeconds'] = (proc_merged['CompletedTime'] - proc_merged['StartedTime']).dt.total_seconds()

print(f"Рассчитана длительность для {len(task_merged)} закрытых задач и {len(proc_merged)} завершенных процессов.")


# Подсчёт незавершённых задач (есть task_created, но нет task_completed)
created_tasks = set(df[df['EventType'] == 'task_created']['TaskId'])
completed_tasks = set(df[df['EventType'] == 'task_completed']['TaskId'])
open_tasks = created_tasks - completed_tasks
print(f"Открытых задач: {len(open_tasks)}")

# Подсчёт незавершённых процессов
started_procs = set(df[df['EventType'] == 'process_started']['ProcessInstanceId'])
completed_procs = set(df[df['EventType'] == 'process_completed']['ProcessInstanceId'])
open_procs = started_procs - completed_procs
print(f"Открытых процессов: {len(open_procs)}")


#Метрики для отчёта
median_check_sec = task_merged[task_merged['ActivityName'] == 'Проверка заявки']['DurationSeconds'].median()
median_approve_sec = task_merged[task_merged['ActivityName'] == 'Согласование руководителем']['DurationSeconds'].median()
p95_standard_sec = np.percentile(proc_merged[proc_merged['RequestType'] == 'standard']['DurationSeconds'], 95)

print(f"Медиана 'Проверка заявки': {median_check_sec/60:.1f} минут")
print(f"Медиана 'Согласование руководителем': {median_approve_sec/3600:.2f} часов")
print(f"95-й перцентиль длительности standard-заявок: {p95_standard_sec/3600:.1f} часов")


anomalies = []
#1: Нарушение сегрегации обязанностей
#Заявитель (requester) не должен закрывать этап "Согласование руководителем"
sod_mask = (df['EventType'] == 'task_completed') & \
           (df['ActivityName'] == 'Согласование руководителем') & \
           (df['Role'] == 'requester')
sod_procs = df[sod_mask]['ProcessInstanceId'].unique()

for pid in sod_procs:
    anomalies.append({'ProcessInstanceId': pid, 'AnomalyType': 'Нарушение сегрегации обязанностей', 'Explanation': "Этап 'Согласование руководителем' закрыт пользователем с ролью 'requester' (заявитель), а не 'manager'. Заявитель не должен утверждать собственную заявку."})
print(f"Найдено процессов с нарушением сегрегации обязанностей: {len(sod_procs)}")

#2: Фиктивное согласование
#Все человеческие задания в процессе выполнены менее чем за 30 секунд
proc_task_counts = task_merged.groupby('ProcessInstanceId').size().reset_index(name='total_tasks')
proc_fast_counts = task_merged[task_merged['DurationSeconds'] < 30].groupby('ProcessInstanceId').size().reset_index(name='fast_tasks')

merged_counts = pd.merge(proc_task_counts, proc_fast_counts, on='ProcessInstanceId', how='left')
merged_counts['fast_tasks'] = merged_counts['fast_tasks'].fillna(0)

# Процесс считается аномальным, если все его задачи (total == fast) выполнены < 30 сек
fast_procs = merged_counts[merged_counts['total_tasks'] == merged_counts['fast_tasks']]['ProcessInstanceId'].unique()

for pid in fast_procs:
    anomalies.append({'ProcessInstanceId': pid, 'AnomalyType': 'Фиктивное согласование', 'Explanation': "Все человеческие задания в процессе выполнены менее чем за 30 секунд."})
print(f"Найдено процессов с фиктивным согласованием: {len(fast_procs)}")

#3: Нарушение SLA срочной заявки
#Срочная заявка обрабатывается дольше, чем 95% обычных заявок
p95_standard = np.percentile(proc_merged[proc_merged['RequestType'] == 'standard']['DurationSeconds'], 95)
print(f"95-й перцентиль длительности standard-заявок: {p95_standard/3600:.1f} часов")

sla_mask = (proc_merged['RequestType'] == 'urgent') & (proc_merged['DurationSeconds'] > p95_standard)
sla_procs = proc_merged[sla_mask]['ProcessInstanceId'].unique()

for pid in sla_procs:
    duration_hours = proc_merged[proc_merged['ProcessInstanceId'] == pid]['DurationSeconds'].iloc[0] / 3600
    anomalies.append({'ProcessInstanceId': pid, 'AnomalyType': 'Нарушение SLA срочной заявки', 'Explanation': f"Заявка типа 'urgent' обрабатывалась более {duration_hours:.0f} часов, что превышает 95-й перцентиль длительности обычных заявок типа 'standard' (~{p95_standard/3600:.0f} часа)."})
print(f"Найдено процессов с нарушением SLA urgent: {len(sla_procs)}")

#4: Пропуск обязательного этапа
# Заявка типа 'contract' должна содержать этап 'Проверка договора'
contract_procs = set(df[df['RequestType'] == 'contract']['ProcessInstanceId'].unique())
legal_review_procs = set(df[df['ActivityName'] == 'Проверка договора']['ProcessInstanceId'].unique())

skipped_legal_procs = list(contract_procs - legal_review_procs)

#топ-3 процесса с наибольшей суммой
skipped_df = df[df['ProcessInstanceId'].isin(skipped_legal_procs)][['ProcessInstanceId', 'Amount']].drop_duplicates()
top_skipped = skipped_df.sort_values('Amount', ascending=False).head(3)['ProcessInstanceId'].tolist()

for pid in top_skipped:
    amount = df[df['ProcessInstanceId'] == pid]['Amount'].iloc[0]
    anomalies.append({'ProcessInstanceId': pid, 'AnomalyType': 'Пропуск обязательного этапа', 'Explanation': f"Заявка типа 'contract' (сумма {amount:.2f} руб.) завершена без этапа 'Проверка договора'."})
print(f"Всего процессов contract без проверки договора: {len(skipped_legal_procs)}")


df_anomalies = pd.DataFrame(anomalies)

output_file = 'anomalies.csv'
df_anomalies.to_csv(output_file, index=False, quoting=1, encoding='utf-8')

print(f"\nФайл '{output_file}' создан")