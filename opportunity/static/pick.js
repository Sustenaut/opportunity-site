// Picks the comment's anchor without reloading: each "Comment" link next to a
// field or section heading sets the form's "On" choice and moves to the form.
// Without this script the same links reload the page with the anchor chosen.
document.addEventListener("click", (e) => {
  const link = e.target.closest("a.pick");
  const select = document.getElementById("anchor");
  if (!link || !select) return;
  e.preventDefault();
  select.value = link.dataset.anchor;
  const form = document.getElementById("comment");
  form.scrollIntoView({ behavior: "smooth", block: "center" });
  form.querySelector("textarea").focus({ preventScroll: true });
});
