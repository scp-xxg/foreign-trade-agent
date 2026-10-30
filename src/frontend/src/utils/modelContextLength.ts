/** A context budget must be explicit for chat providers; never infer it from a model name. */
export function contextLengthIssue(value: unknown, required: boolean): 'required' | 'positive_integer' | null {
  if (value == null || typeof value === 'string' && value.trim() === '') return required ? 'required' : null;
  if (typeof value !== 'number' && typeof value !== 'string') return 'positive_integer';
  const amount = Number(value);
  return Number.isSafeInteger(amount) && amount > 0 ? null : 'positive_integer';
}
