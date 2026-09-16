const dialog = document.querySelector('#cardDialog');
let opener;
const addPath = '/carrinho/adicionar/';

function money(value) {
  return value == null ? 'Preço indisponível' : `R$ ${Number(value).toFixed(2).replace('.', ',')}`;
}

function showVariant(card, variant) {
  const image = document.querySelector('#detailImage');
  image.hidden = !variant.imagem;
  if (variant.imagem) image.src = variant.imagem;
  else image.removeAttribute('src');
  image.alt = `${variant.nome} — ${variant.variante_api_id || variant.carta_api_id}`;
  document.querySelector('#detailCode').textContent = card.carta_api_id;
  document.querySelector('#detailName').textContent = variant.nome;
  document.querySelector('#detailSet').textContent = variant.colecao;
  document.querySelector('#detailEffect').textContent = variant.efeito || 'Sem efeito descrito.';
  document.querySelector('#detailStats').textContent = [variant.categoria, variant.cor, variant.raridade,
    'Poder: ' + (variant.poder ?? '—'), 'Custo: ' + (variant.custo ?? '—')].join(' · ');
  const available = variant.ativo && variant.estoque > 0 && variant.preco != null;
  document.querySelector('#detailAvailability').textContent = available
    ? `${money(variant.preco)} · ${variant.estoque} em estoque`
    : variant.preco == null ? 'Arte disponível para consulta; preço ainda não informado pela fonte.' : 'Arte sem estoque no momento.';
  const form = document.querySelector('#detailAddForm');
  const button = document.querySelector('#detailAddButton');
  form.action = addPath + encodeURIComponent(variant._id);
  button.disabled = !available;
  button.textContent = available ? `Adicionar esta arte · ${money(variant.preco)}` : 'Esta arte não está disponível';
  document.querySelectorAll('#detailVariants button').forEach(option => {
    option.classList.toggle('selected', option.dataset.variant === variant._id);
  });
}

document.querySelectorAll('[data-card]').forEach(button => {
  button.addEventListener('click', () => {
    const card = JSON.parse(button.dataset.card);
    opener = button;
    const picker = document.querySelector('#detailVariants');
    picker.replaceChildren();
    card.variantes.forEach((variant, index) => {
      const option = document.createElement('button');
      option.type = 'button';
      option.dataset.variant = variant._id;
      option.className = 'variant-option';
      option.setAttribute('aria-label', `Selecionar arte ${index + 1}`);
      option.innerHTML = variant.imagem ? `<img src="${variant.imagem}" alt="">` : `<span>Arte ${index + 1}</span>`;
      option.addEventListener('click', () => showVariant(card, variant));
      picker.append(option);
    });
    showVariant(card, card.variantes.find(variant => variant._id === card._id) || card.variantes[0]);
    dialog.showModal();
  });
});
dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) dialog.close(); } });
dialog.addEventListener('close', () => opener?.focus());
document.querySelectorAll('.art-button img').forEach(img => {
  const fallback = () => { img.hidden = true; img.style.display = 'none'; img.parentElement.querySelector('.image-fallback').hidden = false; };
  img.addEventListener('error', fallback);
  if (img.complete && !img.naturalWidth) fallback();
});
document.querySelectorAll('.filters select,.filters input[type=checkbox]').forEach(input => input.addEventListener('change', () => input.form.requestSubmit()));
