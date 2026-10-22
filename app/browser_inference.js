(() => {
  let artifacts;

  async function loadArtifacts() {
    if (!artifacts) {
      artifacts = (async () => {
        if (!window.tf) throw Error('TensorFlow.js did not load. Check your internet connection and reload.');
        await window.tf.ready();
        const [model, response] = await Promise.all([
          window.tf.loadLayersModel('/assets/generator/model.json'),
          fetch('/assets/generator/tokenizer.json', {cache: 'force-cache'})
        ]);
        if (!response.ok) throw Error('The public tokenizer could not be loaded.');
        const tokenizer = await response.json();
        const config = tokenizer.config || {};
        const wordIndex = typeof config.word_index === 'string'
          ? JSON.parse(config.word_index)
          : config.word_index;
        if (model.inputs[0].shape[1] !== 47 || model.outputs[0].shape.at(-1) !== 1168
            || !wordIndex || Object.keys(wordIndex).length !== 1167) {
          model.dispose();
          throw Error('The browser model or tokenizer has unexpected dimensions.');
        }
        const indexWord = new Array(1168);
        for (const [word, index] of Object.entries(wordIndex)) indexWord[index] = word;
        return {model, config, wordIndex, indexWord};
      })().catch(error => {
        artifacts = null;
        throw error;
      });
    }
    return artifacts;
  }

  function tokenize(text, config) {
    let normalized = config.lower ? text.toLowerCase() : text;
    const separator = config.split || ' ';
    for (const character of config.filters || '') {
      normalized = normalized.split(character).join(separator);
    }
    return normalized.split(separator).filter(Boolean);
  }

  async function generate(seed, count, status) {
    if (typeof seed !== 'string' || !seed.trim() || seed.length > 2000) {
      throw Error('Enter a question prefix of 2,000 characters or fewer.');
    }
    if (!Number.isInteger(count) || count < 1 || count > 60) {
      throw Error('Additional words must be a whole number from 1 to 60.');
    }
    const {model, config, wordIndex, indexWord} = await loadArtifacts();
    let tokens = tokenize(seed, config).map(word => wordIndex[word]).filter(index => index !== undefined);
    if (!tokens.length) throw Error('The prompt contains no recognized training words.');
    const words = [];
    for (let i = 0; i < count; i++) {
      const sequence = tokens.slice(-47);
      const padded = Array(47 - sequence.length).fill(0).concat(sequence);
      const input = window.tf.tensor2d([padded], [1, 47], 'int32');
      let output;
      try {
        output = model.predict(input);
        const probabilities = await output.data();
        let selected = 1;
        for (let index = 2; index < probabilities.length; index++) {
          if (probabilities[index] > probabilities[selected]) selected = index;
        }
        if (!indexWord[selected]) throw Error('The tokenizer does not match the model output.');
        words.push(indexWord[selected]);
        tokens.push(selected);
      } finally {
        input.dispose();
        if (output) output.dispose();
      }
    }
    return {
      text: seed.trim() + ' ' + words.join(' '),
      seed,
      model_version: status.model_sha256,
      tokenizer_version: status.tokenizer_sha256,
      status: 'draft_requires_lecturer_approval'
    };
  }

  window.examflowBrowserGenerate = generate;
})();
