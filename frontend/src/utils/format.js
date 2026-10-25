export const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
export function comparePrice(value, prices) {
  if (value === '' || !Number.isFinite(Number(value)) || Number(value) < 0) return '';
  // Compare against the same paise precision the farmer sees in the range.
  const lower = Number(prices.min_price.toFixed(2));
  const upper = Number(prices.max_price.toFixed(2));
  return Number(value) < lower ? 'Below the recommended range' : Number(value) > upper ? 'Above the recommended range' : 'Within the recommended range';
}
export function validate(form) {
  const errors = {};
  const po = form.source === 'price_only' || form.source === 'official';
  const recorded = po && form.mode === 'recorded';
  for (const key of ['crop', 'state', 'district', 'market', 'variety']) if (!form[key]) errors[key] = 'Please select an option.';
  if (!recorded && !form.quality) errors.quality = 'Please select an option.';
  if (po && !['recorded','historical','future'].includes(form.mode)) errors.mode = 'Select a calculation mode.';
  if (po && form.mode !== 'future') {
    const parsed = new Date(form.target_date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.target_date) || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0,10) !== form.target_date) errors.target_date = 'Choose an actual recorded date.';
  }
  if (recorded) {
    if (!form.market_id) errors.market_id = 'Select an exact market identity.';
    return errors;
  }
  if (!Number.isFinite(Number(form.quantity)) || Number(form.quantity) <= 0) errors.quantity = 'Enter a quantity greater than zero.';
  if (!['kg', 'quintal'].includes(form.unit)) errors.unit = 'Select kg or quintal.';
  if (form.transport_cost === '' || !Number.isFinite(Number(form.transport_cost)) || Number(form.transport_cost) < 0) errors.transport_cost = 'Enter a non-negative batch cost, or 0 if none.';
  if (form.source && form.method !== 'auto') errors.method = 'Select the supported evaluated method.';
  for (const key of (po ? ['harvest_date'] : ['harvest_date', 'selling_date'])) {
    const parsed = new Date(form[key]);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form[key]) || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0,10) !== form[key]) errors[key] = 'Choose a valid date.';
  }
  if (!po && !errors.harvest_date && !errors.selling_date && form.selling_date < form.harvest_date) errors.selling_date = 'Selling date must be on or after harvest date.';
  if (po && form.selling_date) errors.selling_date = 'A reporting-session forecast has no calendar selling-date input.';
  if (po && form.mode === 'future' && form.target_date) errors.target_date = 'Future mode supports the next reporting session only; clear the exact date.';
  if (po && !form.market_id) errors.market_id = 'Select a valid market ID.';
  return errors;
}

