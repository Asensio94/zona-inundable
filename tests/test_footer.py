from floodbuild.footer import PROJECTS, footer_nav


def test_footer_lists_the_twelve_projects_and_the_hub():
    assert len(PROJECTS) == 12
    es = footer_nav("es")
    assert 'href="https://asensio94.github.io/terra-aperta/"' in es
    assert es.count("<li") == 12 and es.count("<li><a") == 11
    assert '<li aria-current="page">Construir en zona inundable</li>' in es
    for gone in ("cartera-cotizadas", "cuaderno-campo", "barbechos"):
        assert gone not in es


def test_french_footer_links_french_pages():
    fr = footer_nav("fr")
    assert 'href="https://asensio94.github.io/terra-aperta/fr/"' in fr
    assert "Projets frères" in fr and "depuracion-y-bano/fr/" in fr
