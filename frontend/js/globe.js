/*
    EDUNOVA - Globe Three.js en script classique.
    La bibliothèque globale THREE est chargée avant ce fichier.
    Si WebGL, THREE ou la texture manquent, le poster reste affiché
    silencieusement et aucune animation n'est lancée.
*/
(() => {
  const conteneur = document.querySelector('[data-threejs-placeholder="earth-africa"]');
  if (!conteneur) return;

  const poster = conteneur.querySelector("img");
  const requeteMouvement = window.matchMedia("(prefers-reduced-motion: reduce)");
  let demarre = false;
  let detruit = false;
  let arreterRessources = () => {};
  let ecouteMouvementInitial = null;

  // Rend le poster visible et arrête toute animation.
  const afficherPoster = () => {
    conteneur.dataset.globeState = "poster";
    if (!poster) return;
    poster.hidden = false;
    poster.style.display = "";
  };

  // Masque le poster une fois la scène prête.
  const masquerPoster = () => {
    conteneur.dataset.globeState = "ready";
    if (!poster) return;
    poster.hidden = true;
    poster.style.display = "none";
  };

  // Vérifie la disponibilité de WebGL sans écrire dans la console.
  const webglDisponible = () => {
    try {
      const sonde = document.createElement("canvas");
      return Boolean(
        window.WebGLRenderingContext &&
          (sonde.getContext("webgl2") || sonde.getContext("webgl"))
      );
    } catch (erreur) {
      return false;
    }
  };

  // Convertit une position géographique en vecteur 3D.
  const positionner = (THREE, latitude, longitude, rayon) => {
    const phi = THREE.MathUtils.degToRad(longitude + 180);
    const theta = THREE.MathUtils.degToRad(90 - latitude);
    return new THREE.Vector3(
      -Math.cos(phi) * Math.sin(theta) * rayon,
      Math.cos(theta) * rayon,
      Math.sin(phi) * Math.sin(theta) * rayon
    );
  };

  // Trace les arcs lumineux depuis la Côte d'Ivoire.
  const ajouterArcs = (THREE, globe) => {
    const ressources = [];
    const origine = positionner(THREE, 5.36, -4.01, 1.016);
    const destinations = [
      { lat: 32.5, lon: 11.5, color: 0xe9b44c, lift: 0.36, opacity: 0.9 },
      { lat: 6.5, lon: 3.4, color: 0x19a7a0, lift: 0.2, opacity: 0.8 },
      { lat: -2, lon: 28, color: 0xe9b44c, lift: 0.34, opacity: 0.86 },
      { lat: 30, lon: 31.2, color: 0x19a7a0, lift: 0.28, opacity: 0.78 },
      { lat: -33.5, lon: 18.5, color: 0x19a7a0, lift: 0.3, opacity: 0.75 },
    ];

    destinations.forEach((destination) => {
      const fin = positionner(THREE, destination.lat, destination.lon, 1.016);
      const controle = origine
        .clone()
        .add(fin)
        .normalize()
        .multiplyScalar(1 + destination.lift);
      const courbe = new THREE.QuadraticBezierCurve3(origine, controle, fin);
      const geometrie = new THREE.BufferGeometry().setFromPoints(courbe.getPoints(72));
      const materiau = new THREE.LineBasicMaterial({
        color: destination.color,
        transparent: true,
        opacity: destination.opacity,
        depthWrite: false,
      });
      globe.add(new THREE.Line(geometrie, materiau));
      ressources.push(geometrie, materiau);
    });

    const geometriePoint = new THREE.SphereGeometry(0.018, 16, 16);
    const materiauPoint = new THREE.MeshBasicMaterial({ color: 0xe9b44c });
    const point = new THREE.Mesh(geometriePoint, materiauPoint);
    point.position.copy(positionner(THREE, 5.36, -4.01, 1.028));
    globe.add(point);
    ressources.push(geometriePoint, materiauPoint);
    return ressources;
  };

  // Crée le halo atmosphérique autour de la Terre.
  const creerAtmosphere = (THREE) =>
    new THREE.ShaderMaterial({
      uniforms: {
        glowColor: { value: new THREE.Color(0x19a7a0) },
      },
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
          vView = normalize(-viewPosition.xyz);
          gl_Position = projectionMatrix * viewPosition;
        }
      `,
      fragmentShader: `
        uniform vec3 glowColor;
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          float rim = pow(1.0 - abs(dot(vNormal, vView)), 2.6);
          gl_FragColor = vec4(glowColor, rim * 0.48);
        }
      `,
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
    });

  // Initialise la scène, le renderer et les ressources du globe.
  const demarrer = () => {
    if (demarre || detruit) return;
    demarre = true;

    const THREE = window.THREE;
    if (!THREE || requeteMouvement.matches || !webglDisponible()) {
      afficherPoster();
      if (!THREE || !requeteMouvement.matches) return;
      ecouteMouvementInitial = (evenement) => {
        if (evenement.matches) return;
        requeteMouvement.removeEventListener("change", ecouteMouvementInitial);
        ecouteMouvementInitial = null;
        demarre = false;
        demarrer();
      };
      requeteMouvement.addEventListener("change", ecouteMouvementInitial);
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.className = "globe__image globe-mask";
    canvas.style.display = "block";
    conteneur.insertBefore(canvas, poster || null);

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
    } catch (erreur) {
      canvas.remove();
      afficherPoster();
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 4.2);

    const globe = new THREE.Group();
    globe.rotation.y = THREE.MathUtils.degToRad(-85);
    scene.add(globe);

    scene.add(new THREE.AmbientLight(0x35537d, 1.2));
    const lumiereCle = new THREE.DirectionalLight(0xf2ffff, 2.1);
    lumiereCle.position.set(-3.2, 1.8, 3.6);
    scene.add(lumiereCle);
    const lumiereContour = new THREE.DirectionalLight(0x19a7a0, 0.65);
    lumiereContour.position.set(3, -0.6, -2);
    scene.add(lumiereContour);

    let texture;
    let geometrieTerre;
    let materiauTerre;
    let geometrieAtmosphere;
    let materiauAtmosphere;
    let arcs = [];
    let observateurTaille = null;
    let observateurVisibilite = null;
    let image = 0;
    let enCours = false;
    let derniereHeure = 0;
    let tempsEcoule = 0;
    let pret = false;

    // Redimensionne le renderer et la caméra.
    const redimensionner = () => {
      const largeur = Math.max(1, conteneur.clientWidth);
      const hauteur = Math.max(1, conteneur.clientHeight);
      renderer.setSize(largeur, hauteur, false);
      camera.aspect = largeur / hauteur;
      camera.updateProjectionMatrix();
      if (pret) renderer.render(scene, camera);
    };

    // Dessine une image et poursuit la rotation douce.
    const dessiner = (maintenant) => {
      if (!enCours || detruit) return;
      image = requestAnimationFrame(dessiner);
      const delta = Math.min((maintenant - derniereHeure) / 1000, 0.05);
      derniereHeure = maintenant;
      tempsEcoule += delta;
      if (tempsEcoule > 1.2) globe.rotation.y += delta * 0.018;
      renderer.render(scene, camera);
    };

    // Démarre et arrête la boucle d'animation.
    const demarrerBoucle = () => {
      if (enCours || !pret || detruit) return;
      if (conteneur.dataset.globeState !== "ready") return;
      enCours = true;
      derniereHeure = performance.now();
      image = requestAnimationFrame(dessiner);
    };

    const arreterBoucle = () => {
      enCours = false;
      if (image) cancelAnimationFrame(image);
      image = 0;
    };

    // Perte du contexte WebGL : retour immédiat au poster.
    const surPerteContexte = (evenement) => {
      evenement.preventDefault();
      arreterBoucle();
      afficherPoster();
    };

    // La préférence de mouvement peut changer en cours de session.
    const surMouvement = (evenement) => {
      if (evenement.matches) {
        arreterBoucle();
        afficherPoster();
      } else if (!detruit) {
        masquerPoster();
        demarrerBoucle();
      }
    };

    const surVisibilite = () => {
      if (document.hidden) arreterBoucle();
      else if (!requeteMouvement.matches) demarrerBoucle();
    };

    // Libère les ressources GPU à la fermeture de la page.
    arreterRessources = () => {
      detruit = true;
      arreterBoucle();
      if (observateurVisibilite) observateurVisibilite.disconnect();
      if (observateurTaille) observateurTaille.disconnect();
      window.removeEventListener("resize", redimensionner);
      document.removeEventListener("visibilitychange", surVisibilite);
      requeteMouvement.removeEventListener("change", surMouvement);
      canvas.removeEventListener("webglcontextlost", surPerteContexte, false);
      if (geometrieTerre) geometrieTerre.dispose();
      if (materiauTerre) materiauTerre.dispose();
      if (geometrieAtmosphere) geometrieAtmosphere.dispose();
      if (materiauAtmosphere) materiauAtmosphere.dispose();
      arcs.forEach((ressource) => ressource.dispose());
      if (texture) texture.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };

    requeteMouvement.addEventListener("change", surMouvement);
    document.addEventListener("visibilitychange", surVisibilite);
    canvas.addEventListener("webglcontextlost", surPerteContexte, false);
    window.addEventListener("resize", redimensionner, { passive: true });
    window.addEventListener("pagehide", arreterRessources, { once: true });

    if ("ResizeObserver" in window) {
      observateurTaille = new ResizeObserver(redimensionner);
      observateurTaille.observe(conteneur);
    }

    // Charge la texture locale puis lance l'animation.
    texture = new THREE.TextureLoader().load(
      "assets/earth-blue-marble.jpg",
      () => {
        if (detruit) return;
        pret = true;
        redimensionner();
        masquerPoster();
        if ("IntersectionObserver" in window) {
          observateurVisibilite = new IntersectionObserver(
            (entre) => {
              if (entre.some((element) => element.isIntersecting)) demarrerBoucle();
              else arreterBoucle();
            },
            { threshold: 0.01 }
          );
          observateurVisibilite.observe(conteneur);
        } else {
          demarrerBoucle();
        }
      },
      undefined,
      () => {
        canvas.remove();
        afficherPoster();
      }
    );
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);

    geometrieTerre = new THREE.SphereGeometry(1, 96, 64);
    materiauTerre = new THREE.MeshPhongMaterial({
      map: texture,
      shininess: 12,
      specular: new THREE.Color(0x1b5e68),
    });
    globe.add(new THREE.Mesh(geometrieTerre, materiauTerre));

    geometrieAtmosphere = new THREE.SphereGeometry(1.055, 64, 48);
    materiauAtmosphere = creerAtmosphere(THREE);
    globe.add(new THREE.Mesh(geometrieAtmosphere, materiauAtmosphere));

    arcs = ajouterArcs(THREE, globe);
    redimensionner();
  };

  // Démarre au chargement de la page.
  const lancer = () => {
    conteneur.dataset.globeState = "poster";
    demarrer();
  };

  if (document.readyState === "complete") lancer();
  else window.addEventListener("load", lancer, { once: true });

  window.addEventListener("pagehide", () => {
    if (ecouteMouvementInitial) {
      requeteMouvement.removeEventListener("change", ecouteMouvementInitial);
    }
    arreterRessources();
  });
})();
