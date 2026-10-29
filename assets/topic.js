(() => {
    const search = document.getElementById("problem-search");
    const difficulty = document.getElementById("difficulty-filter");
    const jump = document.getElementById("section-jump");
    const status = document.getElementById("filter-status");
    const empty = document.getElementById("filter-empty");
    const sections = [...document.querySelectorAll(".practice-section")];
    if (!search || !difficulty || !jump || !status || !empty) return;

    // Cache searchable text once; all filtering stays in the browser.
    const entries = sections.map(section => ({
        section,
        count: section.querySelector(".practice-count"),
        rows: [...section.querySelectorAll(".problem-row")].map(row => ({
            element: row,
            text: row.querySelector(".problem-link").textContent.toLowerCase(),
            difficulty: row.dataset.difficulty,
        })),
        openBeforeSearch: section.open,
    }));
    let wasFiltering = false;

    function filter() {
        const query = search.value.trim().toLowerCase();
        const filtering = Boolean(query || difficulty.value);
        let visibleRows = 0;
        let visibleSets = 0;

        for (const entry of entries) {
            if (filtering && !wasFiltering) entry.openBeforeSearch = entry.section.open;
            let count = 0;
            for (const row of entry.rows) {
                const matches = row.text.includes(query)
                    && (!difficulty.value || row.difficulty === difficulty.value);
                row.element.hidden = !matches;
                if (matches) count++;
            }
            entry.section.hidden = count === 0;
            entry.count.textContent = `${count} ${count === 1 ? "problem" : "problems"}`;
            if (filtering && count) entry.section.open = true;
            if (!filtering && wasFiltering) entry.section.open = entry.openBeforeSearch;
            const option = [...jump.options].find(item => item.value === entry.section.id);
            if (option) option.disabled = count === 0;
            visibleRows += count;
            if (count) visibleSets++;
        }
        wasFiltering = filtering;
        empty.hidden = visibleRows !== 0;
        jump.value = "";
        status.textContent = filtering
            ? `${visibleRows} matching ${visibleRows === 1 ? "entry" : "entries"} in ${visibleSets} practice ${visibleSets === 1 ? "set" : "sets"}`
            : `${sections.length} practice sets · Original order`;
    }

    search.addEventListener("input", filter);
    difficulty.addEventListener("change", filter);
    jump.addEventListener("change", () => {
        const section = document.getElementById(jump.value);
        if (section && !section.hidden) {
            section.open = true;
            section.scrollIntoView({ behavior: "instant", block: "start" });
            section.querySelector("summary").focus({ preventScroll: true });
        }
    });
})();
