const dialog = document.querySelector('#cardDialog');
let opener;
document.querySelectorAll('[data-card]').forEach(button => {
  button.addEventListener('click', () => {
    const card = JSON.parse(button.dataset.card);
    opener = button;
    const image = document.querySelector('#detailImage');
    image.hidden = !card.imagem;
    if(card.imagem) image.src = card.imagem;
    else image.removeAttribute('src');
    image.alt = card.nome;
    document.querySelector('#detailCode').textContent = card.carta_api_id;
    document.querySelector('#detailName').textContent = card.nome;
    document.querySelector('#detailSet').textContent = card.colecao;
    document.querySelector('#detailEffect').textContent = card.efeito || 'Sem efeito descrito.';
    document.querySelector('#detailStats').textContent = [card.categoria, card.cor, card.raridade, 'Poder: ' + (card.poder ?? '—'), 'Custo: ' + (card.custo ?? '—')].join(' · ');
    dialog.showModal();
  });
});
dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', e => { if (e.target === dialog) { const r=dialog.getBoundingClientRect(); if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom) dialog.close(); } });
dialog.addEventListener('close', () => opener?.focus());
document.querySelectorAll('.art-button img').forEach(img => {
  const fallback = () => { img.hidden = true; img.style.display = 'none'; img.parentElement.querySelector('.image-fallback').hidden = false; };
  img.addEventListener('error', fallback);
  if (img.complete && !img.naturalWidth) fallback();
});
document.querySelectorAll('.filters select,.filters input[type=checkbox]').forEach(input => input.addEventListener('change', () => input.form.requestSubmit()));
