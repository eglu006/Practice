import pandas as pd

# 0. Загрузка и подготовка данных
df = pd.read_csv('students (1).csv')
df = df.sort_values(by=['ProcessInstanceId', 'EventIndex'])

# 1. Полный список уникальных активностей
unique_activities = df['ActivityName'].unique()
print(f"1. Найдено уникальных активностей: {len(unique_activities)}")
print(unique_activities)

# 2. Начало процесса (process_started)
starts = df[df['EventType'] == 'process_started']['ActivityName'].value_counts()
print("\n2. Начала процесса (process_started):")
print(starts)

# 3. Окончания процесса (process_completed)
endings = df[df['EventType'] == 'process_completed']['ActivityName'].value_counts()
print("\n3. Окончания процесса (process_completed):")
print(endings)
print(f"Сумма окончаний: {endings.sum()}")

# 4. Извлечение маршрутов
traces = df.groupby('ProcessInstanceId')['ActivityName'].apply(lambda x: '>'.join(x)).reset_index()
route_counts = traces['ActivityName'].value_counts().reset_index()
route_counts.columns = ['Route', 'NumberOfCases']
route_counts['Share'] = route_counts['NumberOfCases'] / route_counts['NumberOfCases'].sum()
route_counts = route_counts.sort_values('NumberOfCases', ascending=False).reset_index(drop=True)
route_counts.insert(0, 'Variant', range(1, len(route_counts) + 1))
route_counts.to_csv('variant_template.csv', index=False, encoding='utf-8-sig')

# 5. Извлечение переходов
transitions = []
for pid, group in df.groupby('ProcessInstanceId'):
    activities = group['ActivityName'].tolist()
    for i in range(len(activities) - 1):
        transitions.append((activities[i], activities[i+1]))

trans_df = pd.DataFrame(transitions, columns=['SourceActivity', 'TargetActivity'])
trans_counts = trans_df.value_counts().reset_index(name='Count')
trans_counts.to_csv('student_transitions.csv', index=False, encoding='utf-8-sig')

main_route = 'Регистрация заявки>Первичная проверка>Согласование руководителем>Проверка бюджета>Исполнение закупки>Заявка выполнена'
main_count = route_counts[route_counts['Route'] == main_route]['NumberOfCases'].values[0]
main_share = route_counts[route_counts['Route'] == main_route]['Share'].values[0]
print(f"\nОсновной маршрут: {main_count} случаев ({main_share*100:.1f}%)")

# Развилка 1
print("\n Развилка 1: Первичная проверка")
fork1 = trans_counts[trans_counts['SourceActivity'] == 'Первичная проверка']
print(fork1.to_string(index=False))
print(f"Сумма выходов: {fork1['Count'].sum()}")

# Развилка 2
print("\n Развилка 2: Согласование руководителем")
fork2 = trans_counts[trans_counts['SourceActivity'] == 'Согласование руководителем']
print(fork2.to_string(index=False))
print(f"Сумма выходов: {fork2['Count'].sum()}")

# Развилка 3
print("\n Развилка 3: Проверка бюджета")
fork3 = trans_counts[trans_counts['SourceActivity'] == 'Проверка бюджета']
print(fork3.to_string(index=False))
print(f"Сумма выходов: {fork3['Count'].sum()}")

# После доп. согласования
print("\nПосле: Дополнительное согласование")
after_extra = trans_counts[trans_counts['SourceActivity'] == 'Дополнительное согласование']
print(after_extra.to_string(index=False))
print(f"Сумма выходов: {after_extra['Count'].sum()}")

# 6. Проверка точек срабатывания "Заявка отклонена" и "Заявка отменена" 
print("\n4. Переходы, ведущие к 'Заявка отклонена':")
print(trans_counts[trans_counts['TargetActivity'] == 'Заявка отклонена'])

print("\n5. Переходы, ведущие к 'Заявка отменена':")
print(trans_counts[trans_counts['TargetActivity'] == 'Заявка отменена'])

# А. Подсчёт уникальных экземпляров с необязательными действиями
extra_approval_instances = df[df['ActivityName'] == 'Дополнительное согласование']['ProcessInstanceId'].nunique()
rework_instances = df[df['ActivityName'] == 'Доработка заявки']['ProcessInstanceId'].nunique()

print(f"\nЭкземпляров с 'Дополнительное согласование': {extra_approval_instances} из 1000 ({extra_approval_instances/10}%)")
print(f"\nУникальных экземпляров с 'Доработка заявки': {rework_instances} из 1000 ({rework_instances/10}%)")

# Б. Анализ глубины цикла возвратов (сколько раз доработка встречалась внутри одного ProcessInstanceId)
rework_counts_per_instance = df[df['ActivityName'] == 'Доработка заявки'].groupby('ProcessInstanceId').size()
rework_depth_distribution = rework_counts_per_instance.value_counts().sort_index()

print(f"Всего переходов по циклу: {rework_counts_per_instance.sum()}")
print("Распределение по уникальным экземплярам:")
for depth, count in rework_depth_distribution.items():
    print(f"{depth} доработка подряд: {count} экземпляров")

# 1. Считаем все входы в "Согласование руководителем"
total_transitions_to_approval = trans_counts[
    (trans_counts['TargetActivity'] == 'Согласование руководителем')
]['Count'].sum()

# 2. Считаем общее количество переходов "Первичная проверка" -> "Согласование"
total_check_to_approve = trans_counts[
    (trans_counts['SourceActivity'] == 'Первичная проверка') & 
    (trans_counts['TargetActivity'] == 'Согласование руководителем')
]['Count'].values[0]

# 3. Считаем возвраты из цикла доработки
rework_entries = int(rework_counts_per_instance.sum())

# Истинные первичные входы (первый проход) = общее количество минус возвраты
primary_entries = total_check_to_approve - rework_entries

print(f"\nВсего входов в 'Согласование руководителем': {total_transitions_to_approval}")
print(f"Проверка баланса: Первичные входы ({primary_entries}) + Возвраты ({rework_entries}) = {primary_entries + rework_entries}")


example_ids = [
    "00f3e3a0-9d7d-5eac-98a9-b605b6893e61",
    "009608ae-1567-584a-b67a-c7ec60ec587d",
    "01ae1813-1d99-5524-8f81-77ad5452c33e"
]

for pid in example_ids:
    sub_df = df[df['ProcessInstanceId'] == pid].sort_values('EventIndex')
    if not sub_df.empty:
        amount = sub_df['Amount'].iloc[0]
        route = " > ".join(sub_df['ActivityName'].tolist())
        print(f"\nProcessInstanceId: {pid}")
        print(f"Сумма: {amount:,.2f}")
        print(f"Маршрут: {route}")

print(f"\nИтого экземпляров: {route_counts['NumberOfCases'].sum()}, Сумма долей: {route_counts['Share'].sum():.3f}")