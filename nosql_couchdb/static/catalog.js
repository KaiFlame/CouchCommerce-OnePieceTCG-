const dialog = document.querySelector('#cardDialog');
let opener;

// Adiciona ao carrinho sem recarregar o catálogo, preservando a posição da página.
document.querySelectorAll('.add-form').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('.add-card');
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = '…';
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || 'Não foi possível adicionar a carta.');
      const badge = document.querySelector('.cart-link .badge');
      if (badge) badge.textContent = data.cart_count;
      const toast = document.createElement('div');
      toast.className = 'flash';
      toast.textContent = data.message;
      document.querySelector('.flash-stack')?.append(toast);
      button.textContent = '✓';
      setTimeout(() => { button.disabled = false; button.textContent = originalLabel; toast.remove(); }, 900);
    } catch (error) {
      button.disabled = false;
      button.textContent = originalLabel;
      const toast = document.createElement('div');
      toast.className = 'flash error';
      toast.textContent = error.message;
      document.querySelector('.flash-stack')?.append(toast);
      setTimeout(() => toast.remove(), 4200);
    }
  });
});

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
