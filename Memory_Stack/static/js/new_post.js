// 图片预览功能
document.addEventListener('DOMContentLoaded', function() {
    const imageInput = document.getElementById('images');
    const previewContainer = document.getElementById('imagePreview');
    const maxImages = 9;
    let files = [];

    imageInput.addEventListener('change', function(event) {
        const newFiles = Array.from(event.target.files);
        if (files.length + newFiles.length > maxImages) {
            alert(`最多上传 ${maxImages} 张图片`);
            return;
        }

        newFiles.forEach(file => {
            if (!file.type.match('image/(png|jpeg|jpg|gif)')) {
                alert('仅支持PNG、JPG、JPEG、GIF格式');
                return;
            }

            files.push(file);
            const reader = new FileReader();
            reader.onload = function(e) {
                const container = document.createElement('div');
                container.className = 'preview-container';

                const img = document.createElement('img');
                img.src = e.target.result;
                img.className = 'preview-image';

                const removeBtn = document.createElement('button');
                removeBtn.innerHTML = '×';
                removeBtn.className = 'remove-image';
                removeBtn.onclick = function() {
                    files = files.filter(f => f !== file);
                    container.remove();
                    updateFileInput();
                };

                container.appendChild(img);
                container.appendChild(removeBtn);
                previewContainer.appendChild(container);
            };
            reader.readAsDataURL(file);
        });

        updateFileInput();
    });

    function updateFileInput() {
        const dataTransfer = new DataTransfer();
        files.forEach(file => dataTransfer.items.add(file));
        imageInput.files = dataTransfer.files;
    }
});